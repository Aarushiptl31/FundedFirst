from __future__ import annotations

import csv
import logging
from io import StringIO
from typing import Dict, List

from config import setup_logging
from database import get_user_profile, insert_user_application
from email_sender import send_with_attachment
from agents.email_drafter import draft_cold_email
from profiles.profile_matcher import get_best_profile


setup_logging()
logger = logging.getLogger(__name__)


def _fetch_todays_startups() -> List[Dict[str, object]]:
    """Fetch today's startups ordered by score descending."""
    logger.warning("_fetch_todays_startups: CLI apply flow requires dashboard user context.")
    return []


def _select_startup(startups: List[Dict[str, object]]) -> Dict[str, object] | None:
    """Interactively let the user choose a startup."""
    if not startups:
        print("No startups available for today yet.")
        return None
    print("\nToday's funded startups:\n")
    for idx, s in enumerate(startups, start=1):
        print(
            f"{idx}. {s.get('name')} | Score {s.get('score')} | "
            f"₹{int(s.get('amount_inr') or 0):,} | {s.get('sector')}"
        )
    print()
    while True:
        choice = input("Enter number to view details (or 'q' to quit): ").strip()
        if choice.lower() == "q":
            return None
        if not choice.isdigit():
            print("Please enter a valid number.")
            continue
        idx = int(choice)
        if 1 <= idx <= len(startups):
            return startups[idx - 1]
        print("Out of range, try again.")


def _confirm(prompt: str) -> bool:
    """Ask user for yes/no confirmation."""
    while True:
        ans = input(f"{prompt} (y/n): ").strip().lower()
        if ans in {"y", "yes"}:
            return True
        if ans in {"n", "no"}:
            return False
        print("Please answer y or n.")


def _choose_profile(sector: str) -> Dict[str, object]:
    """Choose best profile automatically or via user selection."""
    auto_profile = get_best_profile(sector)
    print("\nDetected best profile based on sector:")
    print(f"- Key: {auto_profile.get('key')}")
    print(f"- Title: {auto_profile.get('title')}")
    print(f"- Focus sectors: {', '.join(auto_profile.get('sectors', []))}")
    if _confirm("Use this profile"):
        return auto_profile
    print("\nAvailable profiles:")
    profiles = [auto_profile]
    for idx, p in enumerate(profiles, start=1):
        print(f"{idx}. {p.get('title')} ({p.get('key')})")
    return auto_profile


def _build_profile_csv(profile: Dict[str, object]) -> bytes:
    """Create CSV bytes for the selected profile and user details."""
    # get_user_profile returns a plain dict — use .get() not attribute access
    user: Dict[str, object] = {}
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Field", "Value"])
    writer.writerow(["Name",            user.get("name", "")])
    writer.writerow(["Degree",          user.get("degree", "")])
    writer.writerow(["CGPA",            user.get("cgpa", "")])
    writer.writerow(["Graduation Year", user.get("year", "")])
    writer.writerow(["Skills",          user.get("skills", "")])
    writer.writerow(["Experience",      user.get("experience", "")])
    writer.writerow(["Location",        user.get("location", "")])
    writer.writerow(["Github",          user.get("github", "")])
    writer.writerow(["LinkedIn",        user.get("linkedin", "")])
    writer.writerow(["LeetCode",        user.get("leetcode", "")])
    writer.writerow(["Resume Link",     user.get("resume_link", "")])
    writer.writerow(["Certificates",    user.get("certificates", "")])
    writer.writerow(["Target Role",     user.get("role_target", "")])
    writer.writerow(["Notice Period",   user.get("notice_period", "")])
    writer.writerow(["Expected CTC",    user.get("expected_ctc", "")])
    writer.writerow(["Profile Key",     profile.get("key")])
    writer.writerow(["Profile Title",   profile.get("title")])
    writer.writerow(["Profile Focus",   ", ".join(profile.get("sectors", []))])
    return output.getvalue().encode("utf-8")


def run_apply_flow() -> None:
    """Run interactive CLI flow to apply to startups."""
    try:
        startups = _fetch_todays_startups()
        selected = _select_startup(startups)
        if not selected:
            return
        print("\nSelected startup:\n")
        print(f"Name: {selected.get('name')}")
        print(f"Amount: ₹{int(selected.get('amount_inr') or 0):,}")
        print(f"Round: {selected.get('round_type')}")
        print(f"Sector: {selected.get('sector')}")
        print(f"Score: {selected.get('score')}")
        print(f"Summary: {selected.get('summary_what')}")
        print(f"Why apply now: {selected.get('summary_why')}")
        print(f"Best role match: {selected.get('role_match')}")
        if not _confirm("Proceed to apply to this startup"):
            return
        sector = str(selected.get("sector") or "")
        profile = _choose_profile(sector)
        email_data = draft_cold_email(selected, profile)
        subject = email_data.get("subject", "Opportunity with your newly funded startup")
        body = email_data.get("body", "")
        print("\nDraft email subject:")
        print(subject)
        print("\nDraft email body:\n")
        print(body)
        if not _confirm("Send this email now"):
            print("Cancelled sending. You can adjust and run again.")
            return
        csv_bytes = _build_profile_csv(profile)
        if send_with_attachment(subject, body, csv_bytes, "profile.csv"):
            insert_user_application("", {
                "startup_id": int(selected.get("id") or 0),
                "startup_name": str(selected.get("name") or ""),
                "profile_used": str(profile.get("key")),
                "email_subject": subject,
            })
            print("Applied! Follow-up scheduled for Day 4.")
        else:
            print("Failed to send email. Check logs for details.")
    except Exception as exc:
        logger.exception("run_apply_flow: error in apply flow: %s", exc)


__all__ = ["run_apply_flow"]

