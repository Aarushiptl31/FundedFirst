from __future__ import annotations

import logging
import time

import schedule

from config import SCHEDULER_TIME, setup_logging
from email_sender import send_alert_email
from main import run_pipeline


setup_logging()
logger = logging.getLogger(__name__)


def _job_wrapper() -> None:
    """Run the main pipeline with error handling for scheduler."""
    try:
        logger.info("Scheduler: starting daily FundedFirst pipeline")
        run_pipeline(send_digest=True)
    except Exception as exc:
        logger.exception("_job_wrapper: pipeline run failed: %s", exc)
        send_alert_email(
            "FundedFirst pipeline failure",
            "The scheduled FundedFirst pipeline run encountered an error. "
            "Check tracker.log for details.",
        )


def main() -> None:
    """Start the daily scheduler loop."""
    try:
        schedule.every().day.at(SCHEDULER_TIME).do(_job_wrapper)
        logger.info("Scheduler: first run immediately")
        _job_wrapper()
    except Exception as exc:
        logger.exception("main: error during initial scheduling: %s", exc)
    while True:
        try:
            schedule.run_pending()
        except Exception as exc:
            logger.exception("main: error running scheduled jobs: %s", exc)
        time.sleep(60)


if __name__ == "__main__":
    main()

