from __future__ import annotations

import argparse
import sys

from agents.cv_scorer import print_cv_report, score_cv
from config import CV_PDF_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run only CV scorer agent with optional sector override."
    )
    parser.add_argument(
        "--cv",
        default=CV_PDF_PATH,
        help="Path to CV PDF. Defaults to CV_PDF_PATH from .env",
    )
    parser.add_argument(
        "--sector",
        default="General Tech",
        help="Startup sector to score against (e.g., FinTech, AI, HealthTech)",
    )
    parser.add_argument(
        "--startup-name",
        default="Test Startup",
        help="Display name for the report header",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.cv:
        print("[ERROR] No CV path provided.")
        print("Set CV_PDF_PATH in .env or pass --cv <path-to-pdf>.")
        sys.exit(1)

    result = score_cv(args.cv, startup_sector=args.sector)
    print_cv_report(result, startup_name=args.startup_name, sector=args.sector)


if __name__ == "__main__":
    main()
