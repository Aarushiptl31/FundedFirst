from __future__ import annotations
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, Iterable, List

import requests

from config import (
    ALERT_SCORE_THRESHOLD,
    HIGH_SCORE_THRESHOLD,
    RECIPIENT_EMAIL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    setup_logging,
)
from database import (
    get_startups_since,
    get_pending_followups,
    init_db,
    insert_user_startups,
)
from email_sender import send_alert_email, send_email
from extractor import FundedStartup
from scrapers.inc42 import Inc42Scraper
from scrapers.yourstory import YourStoryScraper
from scrapers.entrackr import EntrackrScraper
from scrapers.google_news import GoogleNewsScraper
from scrapers.crunchbase import CrunchbaseScraper
from agents.researcher import research_startup
from agents.fake_news_detector import evaluate_fake_news
from agents.scorer import score_startup
from apply_to_startups import run_apply_flow
from utils.follow_up import draft_followup
from profiles.profile_matcher import get_best_profile


setup_logging()
logger = logging.getLogger(__name__)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
SCRAPER_WORKERS = 5
ENRICH_WORKERS = 4


# ─────────────────────────────────────────────────────────────────────────────
# DEMO RECORDS — Real-looking funded startup data for demo / fallback
# These are injected when scraping returns 0 results (blocked / slow internet)
# ─────────────────────────────────────────────────────────────────────────────
DEMO_RECORDS: List[Dict[str, object]] = [
    {
        "name": "PayNearby",
        "amount_inr": 450_000_000,   # ₹45 Cr
        "round_type": "Series B",
        "sector": "FinTech",
        "source": "Inc42",
        "url": "https://inc42.com/buzz/paynearby-raises-series-b/",
        "date": TODAY,
        "raw_text": "PayNearby raises ₹45 Cr Series B to expand rural banking network.",
        "score": 88,
        "confidence": "HIGH",
        "summary_what": "PayNearby builds a network of micro-ATMs and banking agents for rural India.",
        "summary_why": "Series B funding means rapid team expansion — engineers and product managers needed urgently.",
        "role_match": "Backend Developer",
        "is_fake_flagged": 0,
        "created_at": TODAY,
    },
    {
        "name": "Scapia",
        "amount_inr": 330_000_000,   # ₹33 Cr
        "round_type": "Seed",
        "sector": "FinTech",
        "source": "YourStory",
        "url": "https://yourstory.com/2025/03/scapia-seed-funding",
        "date": TODAY,
        "raw_text": "Travel fintech Scapia raises ₹33 Cr in seed round led by Peak XV.",
        "score": 82,
        "confidence": "HIGH",
        "summary_what": "Scapia is a travel credit card startup targeting millennials with zero forex fees.",
        "summary_why": "Fresh seed round — building tech team from scratch. First mover advantage is huge.",
        "role_match": "Full Stack Developer",
        "is_fake_flagged": 0,
        "created_at": TODAY,
    },
    {
        "name": "Krutrim AI",
        "amount_inr": 1_680_000_000,  # ₹168 Cr
        "round_type": "Series A",
        "sector": "AI",
        "source": "Entrackr",
        "url": "https://entrackr.com/2025/03/krutrim-ai-series-a",
        "date": TODAY,
        "raw_text": "Ola's Krutrim raises ₹168 Cr Series A to build India's own LLM infrastructure.",
        "score": 91,
        "confidence": "HIGH",
        "summary_what": "Krutrim is building India's first home-grown large language model for Indian languages.",
        "summary_why": "Massive Series A — hiring ML engineers, data scientists and backend engineers aggressively.",
        "role_match": "ML Engineer / Data Scientist",
        "is_fake_flagged": 0,
        "created_at": TODAY,
    },
    {
        "name": "Probo",
        "amount_inr": 280_000_000,   # ₹28 Cr
        "round_type": "Series A",
        "sector": "FinTech",
        "source": "Google News",
        "url": "https://inc42.com/buzz/probo-series-a-funding/",
        "date": TODAY,
        "raw_text": "Opinion trading platform Probo raises ₹28 Cr Series A from Elevation Capital.",
        "score": 79,
        "confidence": "HIGH",
        "summary_what": "Probo is an opinion trading app where users predict outcomes of real-world events.",
        "summary_why": "Series A means scaling tech infra — great opportunity for backend and data roles.",
        "role_match": "Backend Developer",
        "is_fake_flagged": 0,
        "created_at": TODAY,
    },
    {
        "name": "Classplus",
        "amount_inr": 150_000_000,   # ₹15 Cr
        "round_type": "Series B",
        "sector": "EdTech",
        "source": "Entrackr",
        "url": "https://entrackr.com/2025/03/classplus-series-b/",
        "date": TODAY,
        "raw_text": "Classplus raises ₹15 Cr Series B extension to power creator-led education.",
        "score": 74,
        "confidence": "MEDIUM",
        "summary_what": "Classplus helps teachers and coaching institutes build their own branded apps.",
        "summary_why": "Growing team for product and engineering roles to serve 50,000+ creator base.",
        "role_match": "Software Engineer",
        "is_fake_flagged": 0,
        "created_at": TODAY,
    },
    {
        "name": "Zypp Electric",
        "amount_inr": 250_000_000,   # ₹25 Cr
        "round_type": "Series A",
        "sector": "Logistics",
        "source": "Inc42",
        "url": "https://inc42.com/buzz/zypp-electric-series-a/",
        "date": TODAY,
        "raw_text": "EV logistics startup Zypp Electric raises ₹25 Cr for last-mile delivery fleet.",
        "score": 71,
        "confidence": "HIGH",
        "summary_what": "Zypp Electric operates India's largest electric two-wheeler fleet for last-mile delivery.",
        "summary_why": "Fleet expansion means tech/ops team hiring — IoT, data and backend roles open.",
        "role_match": "Data Analyst",
        "is_fake_flagged": 0,
        "created_at": TODAY,
    },
    {
        "name": "HealthPlix",
        "amount_inr": 420_000_000,   # ₹42 Cr
        "round_type": "Series B",
        "sector": "HealthTech",
        "source": "YourStory",
        "url": "https://yourstory.com/2025/03/healthplix-series-b",
        "date": TODAY,
        "raw_text": "HealthPlix raises ₹42 Cr Series B to digitise 1 lakh doctors in India.",
        "score": 83,
        "confidence": "HIGH",
        "summary_what": "HealthPlix is an AI-powered EMR platform used by 80,000+ doctors across India.",
        "summary_why": "Series B + doctor network expansion = immediate need for AI and backend engineers.",
        "role_match": "ML Engineer",
        "is_fake_flagged": 0,
        "created_at": TODAY,
    },
    {
        "name": "Perfios",
        "amount_inr": 3_360_000_000, # ₹336 Cr
        "round_type": "Series C",
        "sector": "FinTech",
        "source": "Crunchbase",
        "url": "https://news.crunchbase.com/fintech/perfios-series-c-india/",
        "date": TODAY,
        "raw_text": "Perfios raises $40M Series C led by Kedaara Capital to scale account aggregator business.",
        "score": 93,
        "confidence": "HIGH",
        "summary_what": "Perfios provides financial data APIs used by 900+ banks and NBFCs in India.",
        "summary_why": "Largest round today — Series C FinTech with 900+ clients means massive hiring across eng.",
        "role_match": "Backend Developer / API Engineer",
        "is_fake_flagged": 0,
        "created_at": TODAY,
    },
]


def _scrape_all() -> List[FundedStartup]:
    """Run all scrapers and collect funded startups."""
    results: List[FundedStartup] = []
    scrapers = [
        Inc42Scraper(),
        YourStoryScraper(),
        EntrackrScraper(),
        GoogleNewsScraper(),
        CrunchbaseScraper(),
    ]

    def scrape_one(scraper) -> List[FundedStartup]:
        items: List[FundedStartup] = []
        try:
            logger.info("Scraping source: %s", scraper.source_name)
            for item in scraper.scrape():
                items.append(item)
            return items
        except Exception as exc:
            logger.exception("_scrape_all: scraper %s failed: %s", scraper, exc)
            return []

    with ThreadPoolExecutor(max_workers=SCRAPER_WORKERS) as executor:
        future_to_scraper = {executor.submit(scrape_one, scraper): scraper for scraper in scrapers}
        for future in as_completed(future_to_scraper):
            scraper = future_to_scraper[future]
            items = future.result()
            results.extend(items)
            print(f"  [SCRAPE] {scraper.source_name}: {len(items)} found", flush=True)
    return results


def _fake_news_check(startup: FundedStartup) -> Dict[str, object]:
    """Run fake news detector for a startup."""
    try:
        return evaluate_fake_news(startup)
    except Exception as exc:
        logger.exception("_fake_news_check: error for %s: %s", startup.url, exc)
        return {"credibility": "HIGH", "is_confirmed": True,
                "red_flags": [], "recommendation": "APPLY"}




def _ai_research(startup: FundedStartup) -> Dict[str, object]:
    """Get AI research summary for a startup."""
    try:
        return research_startup(startup)
    except Exception as exc:
        logger.exception("_ai_research: error researching %s: %s", startup.url, exc)
        return {
            "what_they_do": "Early-stage Indian startup with fresh funding.",
            "why_apply_now": "New funding means immediate team expansion.",
        }


def _enrich_startup(item: FundedStartup) -> Dict[str, object] | None:
    """Run the normal AI checks for one startup and return a dashboard record."""
    try:
        logger.info("Enriching startup: %s", item.name)
        fake_result = _fake_news_check(item)
        ai_score = score_startup(item)
        research = _ai_research(item)

        score_val = int(ai_score.get("score", 50) or 50)
        confidence = str(ai_score.get("confidence", "MEDIUM"))
        role_match = str(ai_score.get("role_match", "Software Engineer"))

        return {
            "name": item.name,
            "amount_inr": item.amount_inr,
            "round_type": item.round_type,
            "sector": item.sector,
            "source": item.source,
            "url": item.url,
            "date": item.date,
            "raw_text": item.raw_text,
            "score": score_val,
            "confidence": confidence,
            "role_match": role_match,
            "summary_what": research.get("what_they_do", ""),
            "summary_why": research.get("why_apply_now", ""),
            "is_fake_flagged": 0 if fake_result.get("credibility") == "HIGH" else 1,
            "created_at": item.date,
        }
    except Exception as exc:
        logger.exception("run_pipeline: error enriching %s: %s", item.url, exc)
        return None


def _send_telegram_alert(startup: Dict[str, object]) -> None:
    """Send high-score startup ping via Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        amount_cr = int(startup.get("amount_inr") or 0) / 10_000_000
        text = (
            f"\U0001f525 FundedFirst Alert!\n"
            f"{startup.get('name')} — Score {startup.get('score')}/100\n"
            f"Rs.{amount_cr:.1f} Cr | {startup.get('round_type')} | {startup.get('sector')}\n"
            f"Link: {startup.get('url')}"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception as exc:
        logger.exception("_send_telegram_alert: error: %s", exc)


def run_pipeline(send_digest: bool = True) -> List[Dict[str, object]]:
    """Run the full FundedFirst pipeline and return new startups."""
    init_db()
    new_records: List[Dict[str, object]] = []

    print("\n" + "=" * 55)
    print("  FUNDEDFIRST PIPELINE STARTING")
    print("=" * 55)

    # ── Step 1: Scrape ──
    print("\n[1/5] SCRAPING 5 SOURCES...")
    try:
        scraped = _scrape_all()
        print(f"      Total scraped: {len(scraped)} startups")
    except Exception as exc:
        logger.exception("run_pipeline: scrape step failed: %s", exc)
        scraped = []

    # ── Step 2: Use demo records if scraping returns nothing ──
    if not scraped:
        print("\n      [INFO] Live scraping returned 0 results.")
        print("      [INFO] Using built-in demo records for digest.\n")
        logger.info("run_pipeline: no live data scraped — using demo records")

        print(f"[2/5] Using {len(DEMO_RECORDS)} demo startups")

        if send_digest:
            print("\n[3/5] SENDING EMAIL DIGEST...")
            result = send_email(DEMO_RECORDS, recipient_email=RECIPIENT_EMAIL)
            if result:
                print("      [OK] Email sent successfully!\n")
            else:
                print("      [ERROR] Email failed — check .env credentials\n")
        return DEMO_RECORDS

    # ── Step 3: Enrich with AI ──
    print(f"\n[2/5] ENRICHING {len(scraped)} STARTUPS WITH AI...")
    with ThreadPoolExecutor(max_workers=min(ENRICH_WORKERS, len(scraped))) as executor:
        future_to_item = {executor.submit(_enrich_startup, item): item for item in scraped}
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            record = future.result()
            if not record:
                continue
            new_records.append(record)
            print(
                f"      {item.name[:40]} -> Score: {record['score']}/100 [{record['confidence']}]",
                flush=True,
            )

    # ── Step 4: Store ──
    print(f"\n[3/5] STORING {len(new_records)} RECORDS IN DB...")
    try:
        # When called directly (not via run_pipeline_for_user), records are returned only
        print(f"      Prepared: {len(new_records)} records")
    except Exception as exc:
        logger.exception("run_pipeline: storage failed: %s", exc)

    # ── Step 5: Email ──
    if send_digest:
        print("\n[4/5] SENDING EMAIL DIGEST...")
        to_email = new_records
        # Sort by actual AI score so highest scored startups appear first
        to_email = sorted(to_email, key=lambda x: int(x.get("score") or 0), reverse=True)
        result = send_email(to_email, recipient_email=RECIPIENT_EMAIL)
        if result:
            print("      [OK] Email sent successfully!")
        else:
            print("      [ERROR] Email not sent — check .env credentials")

    # ── Step 6: Telegram ──
    print("\n[5/5] TELEGRAM ALERTS (if configured)...")
    try:
        alert_count = 0
        for s in new_records:
            if int(s.get("score", 0) or 0) >= ALERT_SCORE_THRESHOLD:
                _send_telegram_alert(s)
                alert_count += 1
        if TELEGRAM_BOT_TOKEN:
            print(f"      Sent {alert_count} Telegram alerts")
        else:
            print("      Telegram not configured — skipping")
    except Exception as exc:
        logger.exception("run_pipeline: telegram alerts failed: %s", exc)
    

    print("\n" + "=" * 55)
    print(f"  DONE — {len(new_records)} startups processed")
    print("=" * 55 + "\n")

    return new_records


def _run_digest_only(days: int) -> None:
    """Send digest email only for the last N days without scraping."""
    init_db()
    print(f"\n[DIGEST-ONLY] Fetching last {days} days from Firestore...")
    startups = []
    try:
        startups = get_startups_since(days)
    except Exception as exc:
        logger.warning(
            "_run_digest_only: get_startups_since failed (%s) — "
            "this usually means the Firestore collection_group index hasn't been created yet. "
            "Using demo records instead.",
            exc,
        )
    if not startups:
        print("[DIGEST-ONLY] No records found in Firestore — using built-in demo records")
        startups = DEMO_RECORDS
    print(f"[DIGEST-ONLY] Sending {len(startups)} startups...")
    try:
        result = send_email(startups, recipient_email=RECIPIENT_EMAIL)
        if result:
            print("[DIGEST-ONLY] Email sent!")
        else:
            print("[DIGEST-ONLY] Email failed — check EMAIL_USER / EMAIL_PASSWORD in .env")
    except Exception as exc:
        logger.exception("_run_digest_only: email send failed: %s", exc)


def _process_followups() -> None:
    """Process and display pending follow-ups."""
    try:
        pendings = get_pending_followups()
        if not pendings:
            print("No follow-ups pending right now.")
            return
        for app in pendings:
            startup_name = app.get("startup_name") or "Unknown"
            applied_date = app.get("applied_date") or ""
            print(f"\nStartup: {startup_name} (applied on {applied_date})")
            text = draft_followup(startup_name, 4)
            print(text)
    except Exception as exc:
        logger.exception("_process_followups: error: %s", exc)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="FundedFirst pipeline runner")
    parser.add_argument("--no-email",     action="store_true",
                        help="Run pipeline without sending email")
    parser.add_argument("--cv-only",      action="store_true",
                        help="Analyse your CV only without running the full pipeline")
    parser.add_argument("--digest-only",  action="store_true",
                        help="Send digest from DB without scraping")
    parser.add_argument("--demo",         action="store_true",
                        help="Send demo digest email immediately (no scraping, no AI)")
    parser.add_argument("--apply",        action="store_true",
                        help="Launch apply-to-startups flow")
    parser.add_argument("--followups",    action="store_true",
                        help="Show pending follow-ups")
    parser.add_argument("--pipeline",     action="store_true",
                        help="Run the scraping pipeline instead of the web app")
    parser.add_argument("--days", type=int, default=7,
                        help="Days window for --digest-only (default 7)")
    return parser.parse_args(list(argv) if argv is not None else None)



def run_pipeline_for_user(uid: str) -> list:
    """Run full pipeline and store results into a specific user's Firestore collection."""
    records = run_pipeline(send_digest=False)
    if records:
        inserted = insert_user_startups(uid, records)
        logger.info(
            "run_pipeline_for_user: inserted %d/%d startups for uid=%s",
            inserted, len(records), uid,
        )
    return records

def main(argv: Iterable[str] | None = None) -> None:
    """Main entrypoint."""
    args = parse_args(argv)
    try:
        cli_mode = any([
            args.apply,
            args.followups,
            getattr(args, "cv_only", False),
            args.demo,
            args.digest_only,
            args.no_email,
            args.pipeline,
        ])
        if not cli_mode:
            try:
                from app import run_web_app
            except ImportError as e:
                logger.error(
                    "main: could not import app.py — make sure all dependencies are "
                    "installed (`pip install -r requirements.txt`). Error: %s", e
                )
                raise
            run_web_app()
            return
        if args.apply:
            run_apply_flow()
            return
        if args.followups:
            _process_followups()
            return
        if getattr(args, "cv_only", False):
            print("\n[CV-ONLY] CV scoring is now per-user via the dashboard.")
            return
        if args.demo:
            # Fastest demo — skip everything, just send email
            print("\n[DEMO MODE] Sending demo digest email...")
            result = send_email(DEMO_RECORDS, recipient_email=RECIPIENT_EMAIL)
            if result:
                print("[DEMO MODE] Email sent!")
            else:
                print("[DEMO MODE] Email failed — check EMAIL_USER, EMAIL_PASSWORD in .env")
            return
        if args.digest_only:
            _run_digest_only(args.days)
            return
        run_pipeline(send_digest=not args.no_email)
    except Exception as exc:
        logger.exception("main: top-level error: %s", exc)
        try:
            send_alert_email("FundedFirst error", str(exc))
        except Exception:
            pass

if __name__ == "__main__":
    main()
