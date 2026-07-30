"""Standalone persistent database-queue worker."""
import logging
import signal
import time

from app import create_app, db
from app.services.tasks import process_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ops-dras-worker")
app = create_app()
running = True

with app.app_context():
    recovered = db.recover_interrupted_tasks()
    if recovered:
        logger.warning("requeued %s interrupted task(s)", recovered)


def stop(*_args):
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

while running:
    with app.app_context():
        task = db.claim_next_task()
    if task:
        logger.info("processing task %s (%s), attempt %s", task["id"], task["task_type"], task["attempts"])
        process_task(app, task)
    else:
        time.sleep(app.config["WORKER_POLL_INTERVAL"])
