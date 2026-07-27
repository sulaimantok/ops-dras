"""
Background execution of long-running Cinder operations so HTTP requests
from the UI return immediately. Task progress/state is persisted in SQLite
(app.db.tasks) so any worker process/thread can report status back to the
polling frontend.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from app import db
from app.openstack_client import OpenStackClient, OpenStackError

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ops-dras-task")


def submit_backup(app, task_id, cluster_id, volume_id, volume_name):
    _executor.submit(_run_backup, app, task_id, cluster_id, volume_id, volume_name)


def submit_restore(app, task_id, source_cluster_id, dest_cluster_id, source_backup_id, dest_volume_id=None):
    _executor.submit(
        _run_restore, app, task_id, source_cluster_id, dest_cluster_id, source_backup_id, dest_volume_id
    )


def _run_backup(app, task_id, cluster_id, volume_id, volume_name):
    with app.app_context():
        db.update_task(task_id, status="running", message="Requesting backup from source cluster")
        try:
            source_cfg = db.get_cluster(cluster_id)
            if not source_cfg:
                raise OpenStackError("source cluster no longer exists")
            client = OpenStackClient(source_cfg, timeout=app.config["OPENSTACK_TIMEOUT"])
            backup = client.create_backup(volume_id, name=f"ops-dras-{volume_name or volume_id[:8]}")
            backup_id = backup["id"]
            db.update_task(
                task_id,
                source_backup_id=backup_id,
                message=f"Backup {backup_id} created, waiting for completion",
            )

            client.wait_for_backup_status(
                backup_id,
                interval=app.config["BACKUP_POLL_INTERVAL"],
                timeout=app.config["BACKUP_POLL_TIMEOUT"],
            )
            db.update_task(
                task_id,
                status="success",
                message=f"Backup {backup_id} completed and available",
            )
        except OpenStackError as exc:
            logger.exception("backup task %s failed", task_id)
            db.update_task(task_id, status="failed", message=str(exc))
        except Exception as exc:  # noqa: BLE001 - surface any unexpected failure to the UI
            logger.exception("backup task %s crashed", task_id)
            db.update_task(task_id, status="failed", message=f"Unexpected error: {exc}")


def _run_restore(app, task_id, source_cluster_id, dest_cluster_id, source_backup_id, dest_volume_id=None):
    with app.app_context():
        try:
            source_cfg = db.get_cluster(source_cluster_id)
            dest_cfg = db.get_cluster(dest_cluster_id)
            if not source_cfg or not dest_cfg:
                raise OpenStackError("source or destination cluster no longer exists")

            if source_cluster_id == dest_cluster_id:
                # export_record/import_record move a backup's metadata record
                # into a DIFFERENT Cinder database. Re-importing a record that
                # already lives in the same database fails with "Backup
                # already exists in database" — so for a same-cluster restore
                # (e.g. bringing back a deleted volume), skip straight to
                # restore_backup using the original backup id.
                db.update_task(task_id, status="running", message="Restoring in place on the same cluster")
                client = OpenStackClient(source_cfg, timeout=app.config["OPENSTACK_TIMEOUT"])
                restore_result = client.restore_backup(source_backup_id, volume_id=dest_volume_id)
                result_volume_id = restore_result.get("volume_id")
                db.update_task(
                    task_id,
                    dest_backup_id=source_backup_id,
                    dest_volume_id=result_volume_id,
                    status="success",
                    message=f"Restore triggered in place on {source_cfg['name']} (volume {result_volume_id})",
                )
                return

            db.update_task(task_id, status="running", message="Exporting backup record from source cluster")
            source_client = OpenStackClient(source_cfg, timeout=app.config["OPENSTACK_TIMEOUT"])
            dest_client = OpenStackClient(dest_cfg, timeout=app.config["OPENSTACK_TIMEOUT"])

            # Step 1: export metadata record from the source cluster
            record = source_client.export_record(source_backup_id)
            db.update_task(task_id, message="Importing backup record into destination cluster")

            # Step 2: import metadata record into the destination cluster
            imported = dest_client.import_record(
                backup_service=record["backup_service"],
                backup_url=record["backup_url"],
            )
            dest_backup_id = imported["id"]
            db.update_task(
                task_id,
                dest_backup_id=dest_backup_id,
                message=f"Record imported as {dest_backup_id}, triggering restore",
            )

            # Step 3: trigger restore on the destination cluster
            restore_result = dest_client.restore_backup(dest_backup_id, volume_id=dest_volume_id)
            result_volume_id = restore_result.get("volume_id")
            db.update_task(
                task_id,
                dest_volume_id=result_volume_id,
                status="success",
                message=f"Restore triggered on destination cluster (volume {result_volume_id})",
            )
        except OpenStackError as exc:
            logger.exception("restore task %s failed", task_id)
            db.update_task(task_id, status="failed", message=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("restore task %s crashed", task_id)
            db.update_task(task_id, status="failed", message=f"Unexpected error: {exc}")
