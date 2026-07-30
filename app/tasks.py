"""Persistent task execution shared by the standalone worker."""
import logging

from app import db
from app.openstack_client import OpenStackClient, OpenStackError

logger = logging.getLogger(__name__)


def process_task(app, task):
    with app.app_context():
        try:
            if task["task_type"] == "backup":
                _run_backup(app, task)
            elif task["task_type"] == "restore":
                _run_restore(app, task)
            else:
                raise OpenStackError(f"Unsupported task type: {task['task_type']}", code="invalid_task")
        except OpenStackError as exc:
            _handle_failure(app, task, exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("task %s crashed", task["id"])
            _handle_failure(
                app, task,
                OpenStackError(f"Unexpected error: {exc}", code="unexpected_error", retryable=False),
            )


def _handle_failure(app, task, exc):
    logger.error("task %s failed: %s", task["id"], exc)
    attempts = task["attempts"]
    if exc.retryable and attempts < task["max_attempts"]:
        delay = app.config["TASK_RETRY_BASE_SECONDS"] * (2 ** max(0, attempts - 1))
        db.retry_task(
            task["id"], f"Temporary failure; retry {attempts + 1}/{task['max_attempts']} in {delay}s",
            error_code=exc.code, error_detail=str(exc), delay_seconds=delay,
        )
        return
    db.update_task(
        task["id"], status="failed", stage="failed", message=str(exc),
        error_code=exc.code, error_detail=str(exc), finished_at=db.text("CURRENT_TIMESTAMP"),
    )
    db.create_audit_log(task.get("created_by"), "task.failed", "task", task["id"], str(exc))


def _run_backup(app, task):
    task_id = task["id"]
    db.update_task(task_id, stage="creating_backup", message="Requesting backup from source cluster")
    source_cfg = db.get_cluster(task["source_cluster_id"])
    if not source_cfg:
        raise OpenStackError("Source cluster no longer exists", code="cluster_missing")
    client = OpenStackClient(source_cfg, timeout=app.config["OPENSTACK_TIMEOUT"])
    backup_id = task.get("source_backup_id")
    if not backup_id:
        backup = client.create_backup(
            task["volume_id"], name=f"ops-dras-{task['volume_name'] or task['volume_id'][:8]}"
        )
        backup_id = backup["id"]
        db.update_task(
            task_id, source_backup_id=backup_id, stage="waiting_backup",
            message=f"Backup {backup_id} created, waiting for completion",
        )
    client.wait_for_backup_status(
        backup_id, interval=app.config["BACKUP_POLL_INTERVAL"],
        timeout=app.config["BACKUP_POLL_TIMEOUT"],
    )
    db.update_task(
        task_id, status="succeeded", stage="succeeded", error_code=None, error_detail=None,
        message=f"Backup {backup_id} completed and available", finished_at=db.text("CURRENT_TIMESTAMP"),
    )
    db.create_audit_log(task.get("created_by"), "backup.succeeded", "task", task_id)


def _run_restore(app, task):
    task_id = task["id"]
    source_cfg = db.get_cluster(task["source_cluster_id"])
    dest_cfg = db.get_cluster(task["dest_cluster_id"])
    if not source_cfg or not dest_cfg:
        raise OpenStackError("Source or destination cluster no longer exists", code="cluster_missing")

    if task["source_cluster_id"] == task["dest_cluster_id"]:
        db.update_task(task_id, stage="restoring", message="Restoring in place on the same cluster")
        client = OpenStackClient(source_cfg, timeout=app.config["OPENSTACK_TIMEOUT"])
        result = client.restore_backup(task["source_backup_id"], volume_id=task.get("dest_volume_id"))
        result_volume_id = result.get("volume_id")
        db.update_task(
            task_id, dest_backup_id=task["source_backup_id"], dest_volume_id=result_volume_id,
            status="succeeded", stage="succeeded", message=f"Restore triggered in place (volume {result_volume_id})",
            finished_at=db.text("CURRENT_TIMESTAMP"), error_code=None, error_detail=None,
        )
        db.create_audit_log(task.get("created_by"), "restore.succeeded", "task", task_id)
        return

    source_client = OpenStackClient(source_cfg, timeout=app.config["OPENSTACK_TIMEOUT"])
    dest_client = OpenStackClient(dest_cfg, timeout=app.config["OPENSTACK_TIMEOUT"])
    db.update_task(task_id, stage="exporting", message="Exporting backup record from source cluster")
    dest_backup_id = task.get("dest_backup_id")
    if not dest_backup_id:
        record = source_client.export_record(task["source_backup_id"])
        db.update_task(task_id, stage="importing", message="Importing backup record into destination cluster")
        imported = dest_client.import_record(record["backup_service"], record["backup_url"])
        dest_backup_id = imported["id"]
        db.update_task(task_id, dest_backup_id=dest_backup_id, stage="restoring", message="Triggering restore")
    result = dest_client.restore_backup(dest_backup_id, volume_id=task.get("dest_volume_id"))
    result_volume_id = result.get("volume_id")
    db.update_task(
        task_id, dest_volume_id=result_volume_id, status="succeeded", stage="succeeded",
        message=f"Restore triggered on destination cluster (volume {result_volume_id})",
        finished_at=db.text("CURRENT_TIMESTAMP"), error_code=None, error_detail=None,
    )
    db.create_audit_log(task.get("created_by"), "restore.succeeded", "task", task_id)
