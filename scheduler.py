#!/usr/bin/env python3
"""
Scheduled Pipeline Runner
Runs the pipeline at 8am GMT every day.

Usage:
    python scheduler.py          # Run scheduler daemon
    python scheduler.py --once   # Run pipeline once immediately
"""

import schedule
import time
import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path

# Setup logging
LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_pipeline():
    """Execute the pipeline."""
    logger.info("=" * 60)
    logger.info(f"Starting scheduled pipeline run at {datetime.now().isoformat()}")
    logger.info("=" * 60)

    try:
        # Get the project root
        project_root = Path(__file__).parent
        venv_python = project_root / '.venv' / 'bin' / 'python'

        # Use system python if venv not found
        python_path = str(venv_python) if venv_python.exists() else sys.executable

        # Run the pipeline
        result = subprocess.run(
            [python_path, 'run_pipeline.py', '--no-dashboard', '--headless'],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout
        )

        if result.returncode == 0:
            logger.info("Pipeline completed successfully")
            logger.info(f"Output: {result.stdout[-500:] if len(result.stdout) > 500 else result.stdout}")
        else:
            logger.error(f"Pipeline failed with code {result.returncode}")
            logger.error(f"Error: {result.stderr}")

    except subprocess.TimeoutExpired:
        logger.error("Pipeline timed out after 30 minutes")
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Scheduled Pipeline Runner')
    parser.add_argument('--once', action='store_true', help='Run pipeline once immediately')
    args = parser.parse_args()

    if args.once:
        run_pipeline()
        return

    # Schedule for 8:00 AM GMT (UTC)
    # Note: schedule library uses local time, so adjust if needed
    schedule.every().day.at("08:00").do(run_pipeline)

    logger.info("Scheduler started")
    logger.info("Pipeline scheduled to run daily at 08:00 GMT")
    logger.info("Press Ctrl+C to stop")

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


if __name__ == '__main__':
    main()
