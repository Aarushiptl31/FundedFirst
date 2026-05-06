from __future__ import annotations
import logging
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import (
    FIREBASE_WEB_API_KEY, FIREBASE_AUTH_DOMAIN, FIREBASE_PROJECT_ID,
    FIREBASE_STORAGE_BUCKET, FIREBASE_MESSAGING_SENDER_ID, FIREBASE_APP_ID,
    HIGH_SCORE_THRESHOLD, APP_DEBUG, APP_HOST, APP_PORT, setup_logging,
)
from database import (
    init_db, verify_firebase_token, get_user_profile, save_user_profile,
    get_user_startups, get_user_applications, insert_user_application,
)

app = Flask(__name__)
# SECRET_KEY is required for Flask session signing; generate one if not in env
import os as _os
app.secret_key = _os.environ.get("FLASK_SECRET_KEY") or _os.urandom(32)
CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})
setup_logging()
logger = logging.getLogger(__name__)
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads" / "cvs"
ALLOWED_CV_EXTENSIONS = {".pdf", ".doc", ".docx"}

_status: Dict[str, Any] = {
    "running": False, "last_run": None, "last_count": 0,
    "message": "Click 'Run Pipeline' to scrape latest startups",
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_payload() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _allowed_cv(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_CV_EXTENSIONS


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return render_template("dashboard.html"), 404


@app.errorhandler(Exception)
def server_error(error):
    logger.exception("Unhandled request error on %s: %s", request.path, error)
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error"}), 500
    return render_template("dashboard.html"), 500


def _require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        user = {}
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user = verify_firebase_token(token)
        if not user or not user.get("uid"):
            session_user = session.get("user") or {}
            if session_user.get("uid"):
                logger.warning(
                    "_require_auth: using Flask session fallback for %s",
                    request.path,
                )
                user = session_user
        if not user or not user.get("uid"):
            return jsonify({"error": "Invalid or expired token"}), 401
        request.user = user
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/firebase-config")
def firebase_config():
    return jsonify({
        "apiKey": FIREBASE_WEB_API_KEY,
        "authDomain": FIREBASE_AUTH_DOMAIN,
        "projectId": FIREBASE_PROJECT_ID,
        "storageBucket": FIREBASE_STORAGE_BUCKET,
        "messagingSenderId": FIREBASE_MESSAGING_SENDER_ID,
        "appId": FIREBASE_APP_ID,
    })


@app.route("/api/auth/verify", methods=["POST"])
def auth_verify():
    data = _json_payload()
    token = data.get("idToken", "")
    if not token:
        logger.warning("auth_verify: missing idToken")
        return jsonify({"error": "No token"}), 400
    user = verify_firebase_token(token)
    if not user or not user.get("uid"):
        logger.warning("auth_verify: Firebase token verification failed")
        return jsonify({
            "error": "Could not verify sign-in. "
                     "Check that FIREBASE_CREDENTIALS_PATH is correct in .env "
                     "and that firebase_credentials.json exists."
        }), 401
    uid = user["uid"]
    existing = get_user_profile(uid)
    if not existing:
        created_profile = {
            "email": user.get("email", ""),
            "name": user.get("name", ""),
            "picture": user.get("picture", ""),
            "created_at": _utc_iso(),
            "skills": "", "degree": "", "cgpa": "", "year": "",
            "experience": "", "location": "", "github": "",
            "linkedin": "", "leetcode": "", "resume_link": "",
            "cv_filename": "", "cv_path": "",
            "certificates": "", "role_target": "", "notice_period": "",
            "expected_ctc": "",
        }
        if not save_user_profile(uid, created_profile):
            logger.warning("auth_verify: profile save failed for uid=%s", uid)
            existing = created_profile
    profile = get_user_profile(uid) or existing or {}
    session["user"] = user
    session.permanent = True
    logger.info("auth_verify: verified Firebase user uid=%s email=%s", uid, user.get("email", ""))
    return jsonify({"user": user, "profile": profile})


@app.route("/api/profile", methods=["GET"])
@_require_auth
def api_profile():
    uid = request.user["uid"]
    profile = get_user_profile(uid)
    return jsonify({**request.user, **profile})


@app.route("/api/profile", methods=["PUT"])
@_require_auth
def api_update_profile():
    uid = request.user["uid"]
    data = _json_payload()
    allowed_fields = [
        "name", "degree", "cgpa", "year", "skills", "experience",
        "location", "github", "linkedin", "leetcode", "resume_link",
        "certificates", "role_target", "notice_period", "expected_ctc",
    ]
    update = {k: v for k, v in data.items() if k in allowed_fields}
    if update:
        save_user_profile(uid, update)
    return jsonify({"ok": True})


@app.route("/api/profile/cv", methods=["POST"])
@_require_auth
def api_upload_cv():
    uid = request.user["uid"]
    file = request.files.get("cv")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "No CV file uploaded"}), 400
    if not _allowed_cv(file.filename):
        return jsonify({"ok": False, "error": "Upload a PDF, DOC, or DOCX file"}), 400

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(file.filename)
    filename = f"{uid}_{int(datetime.now(timezone.utc).timestamp())}_{safe_name}"
    path = UPLOAD_DIR / filename
    file.save(path)

    update = {
        "cv_filename": safe_name,
        "cv_path": str(path),
        "resume_link": str(path),
    }
    save_user_profile(uid, update)
    return jsonify({"ok": True, **update})


@app.route("/api/startups")
@_require_auth
def api_startups():
    uid = request.user["uid"]
    startups = get_user_startups(uid)
    if not startups:
        startups = _get_demo_startups()
    return jsonify({"startups": startups, "threshold": HIGH_SCORE_THRESHOLD, "status": _status})


@app.route("/api/run", methods=["POST"])
@_require_auth
def api_run():
    if _status["running"]:
        return jsonify({"ok": False, "message": "Already running"})
    uid = request.user["uid"]
    threading.Thread(target=_run_pipeline_bg, args=(uid,), daemon=True).start()
    return jsonify({"ok": True, "message": "Pipeline started"})


@app.route("/api/status")
def api_status():
    return jsonify(_status)


@app.route("/api/apply", methods=["POST"])
@_require_auth
def api_apply():
    uid = request.user["uid"]
    data = _json_payload()
    name = data.get("name", "")
    startups = get_user_startups(uid) or _get_demo_startups()
    startup = next((s for s in startups if s.get("name") == name), None)
    if not startup:
        return jsonify({"ok": False, "error": "Startup not found"}), 404
    try:
        from agents.email_drafter import draft_cold_email
        from profiles.profile_matcher import get_best_profile
        from utils.cgpa_handler import get_cgpa_strategy
        profile = get_user_profile(uid)
        profile_dict = get_best_profile(startup.get("sector", ""))
        cgpa_raw = profile.get("cgpa", "0") or "0"
        try:
            cgpa_val = float(cgpa_raw)
        except ValueError:
            cgpa_val = 0.0
        cgpa_strategy = get_cgpa_strategy(cgpa_val)
        result = draft_cold_email(startup, {
            "name": profile.get("name", ""),
            "degree": profile.get("degree", ""),
            "cgpa": profile.get("cgpa", ""),
            "year": profile.get("year", ""),
            "skills": profile.get("skills", ""),
            "experience": profile.get("experience", ""),
            "role_target": profile.get("role_target", ""),
            "location": profile.get("location", ""),
            "github": profile.get("github", ""),
            "linkedin": profile.get("linkedin", ""),
            "resume_link": profile.get("resume_link", ""),
            "certificates": profile.get("certificates", ""),
            "notice_period": profile.get("notice_period", ""),
            "expected_ctc": profile.get("expected_ctc", ""),
            "cgpa_strategy": cgpa_strategy.get("strategy", "medium"),
            "best_role": profile_dict.get("role", "Software Engineer"),
        })
        subject = result.get("subject", "")
        body = result.get("body", "")
        if subject and body:
            return jsonify({
                "ok": True,
                "subject": subject,
                "body": body,
                "ai": bool(result.get("generated_with_ai")),
            })
    except Exception as e:
        logger.warning("AI drafter failed: %s", e)
    subject, body = _build_email_fallback(startup, get_user_profile(uid))
    return jsonify({"ok": True, "subject": subject, "body": body, "ai": False})


@app.route("/api/mark-applied", methods=["POST"])
@_require_auth
def api_mark_applied():
    uid = request.user["uid"]
    data = _json_payload()
    startup_name = data.get("name", "")
    subject = data.get("subject", "")
    if not startup_name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    insert_user_application(uid, {
        "startup_name": startup_name,
        "profile_used": get_user_profile(uid).get("role_target", ""),
        "email_subject": subject or f"Application for {startup_name}",
        "notes": f"Applied from dashboard at {datetime.now().isoformat()}",
    })
    return jsonify({"ok": True})


@app.route("/api/applications")
@_require_auth
def api_applications():
    uid = request.user["uid"]
    apps = get_user_applications(uid)
    return jsonify({"applications": apps})


@app.route("/api/history")
@_require_auth
def api_history():
    uid = request.user["uid"]
    apps = get_user_applications(uid)
    startups = get_user_startups(uid) or _get_demo_startups()
    scores = [int(s.get("score") or 0) for s in startups if s.get("score")]
    avg_score = int(round(sum(scores) / len(scores))) if scores else 0
    latest = startups[0] if startups else {}
    return jsonify({
        "applications": apps,
        "cv_summary": {
            "latest_score": latest.get("score"),
            "latest_grade": latest.get("confidence", ""),
            "latest_verdict": latest.get("cv_verdict", ""),
            "avg_score": avg_score,
            "scored_count": len(scores),
            "latest_missing_skills": latest.get("cv_missing_skills", []),
        },
    })


def _run_pipeline_bg(uid: str):
    global _status
    _status["running"] = True
    _status["message"] = "Scraping 5 sources..."
    try:
        from main import run_pipeline_for_user
        records = run_pipeline_for_user(uid)
        _status["last_count"] = len(records)
        _status["last_run"] = datetime.now().strftime("%d %b %Y %I:%M %p")
        _status["message"] = f"Done — {len(records)} startups processed"
    except Exception as exc:
        logger.exception("Pipeline error: %s", exc)
        _status["message"] = "Pipeline completed with some errors"
        _status["last_run"] = datetime.now().strftime("%d %b %Y %I:%M %p")
    finally:
        _status["running"] = False


def _build_email_fallback(startup: dict, profile: dict) -> tuple:
    import re
    name = profile.get("name", "Candidate")
    degree = profile.get("degree", "Engineering")
    skills = profile.get("skills", "Python")
    experience = profile.get("experience", "projects")
    location = profile.get("location", "India")
    github = profile.get("github", "")
    linkedin = profile.get("linkedin", "")
    resume = profile.get("resume_link", "")
    role = startup.get("role_match", "Software Engineer")
    notice = profile.get("notice_period", "Immediately")
    ctc = profile.get("expected_ctc", "")
    s_name = startup.get("name", "your company")
    amount_cr = float(startup.get("amount_inr") or 0) / 10_000_000
    round_type = startup.get("round_type", "funding")
    sector = startup.get("sector", "")
    what = startup.get("summary_what", f"your work in {sector}")
    why = startup.get("summary_why", "Fresh funding means team growth.")
    try:
        cgpa = float(profile.get("cgpa") or 0)
        cgpa_line = (
            f"My CGPA of {profile['cgpa']} reflects strong academics." if cgpa >= 8.0
            else f"I have a {profile['cgpa']} CGPA with hands-on experience." if cgpa >= 7.0
            else ""
        )
    except Exception:
        cgpa_line = ""
    links = " | ".join(filter(None, [
        f"GitHub: {github}" if github else "",
        f"LinkedIn: {linkedin}" if linkedin else "",
        f"Resume: {resume}" if resume else "",
    ]))
    avail = f"Notice period: {notice}" + (f" | Expected CTC: {ctc}" if ctc else "")
    subject = f"Application for {role} — {name} | {degree}"
    body = f"""Dear Hiring Team at {s_name},

I came across {s_name}'s Rs.{amount_cr:.1f} Cr {round_type} and was genuinely excited — {what}

{why}

I am {name}, a {degree} student from {location}. My core skills include {skills}, with experience through {experience}.
{cgpa_line}
I am actively looking for a {role} role and believe my background is a strong fit for {s_name}.

{links}
{avail}

I would love a quick 15-minute call. Looking forward to hearing from you.

Best regards,
{name}"""
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return subject, body


def _get_demo_startups() -> List[Dict[str, Any]]:
    return [
        {"name": "Perfios", "amount_inr": 3360000000, "round_type": "Series C", "sector": "FinTech",
         "score": 93, "confidence": "HIGH", "source": "Crunchbase",
         "summary_what": "Financial data API platform for 900+ banks.",
         "summary_why": "Series C + massive scale = immediate hiring.",
         "role_match": "Backend Developer", "url": "https://inc42.com", "date": "2025-03-20"},
        {"name": "Krutrim AI", "amount_inr": 1680000000, "round_type": "Series A", "sector": "AI",
         "score": 91, "confidence": "HIGH", "source": "Entrackr",
         "summary_what": "India's first home-grown LLM for Indian languages.",
         "summary_why": "Massive Series A — hiring ML engineers aggressively.",
         "role_match": "ML Engineer", "url": "https://entrackr.com", "date": "2025-03-20"},
        {"name": "PayNearby", "amount_inr": 450000000, "round_type": "Series B", "sector": "FinTech",
         "score": 88, "confidence": "HIGH", "source": "Inc42",
         "summary_what": "Micro-ATM network for rural India.",
         "summary_why": "Series B means rapid team expansion.",
         "role_match": "Backend Developer", "url": "https://inc42.com", "date": "2025-03-20"},
        {"name": "HealthPlix", "amount_inr": 420000000, "round_type": "Series B", "sector": "HealthTech",
         "score": 83, "confidence": "HIGH", "source": "YourStory",
         "summary_what": "AI-powered EMR for 80,000+ doctors.",
         "summary_why": "Series B expansion = AI and backend roles.",
         "role_match": "ML Engineer", "url": "https://yourstory.com", "date": "2025-03-20"},
        {"name": "Scapia", "amount_inr": 330000000, "round_type": "Seed", "sector": "FinTech",
         "score": 82, "confidence": "HIGH", "source": "YourStory",
         "summary_what": "Travel credit card with zero forex fees.",
         "summary_why": "Fresh seed — building tech team from scratch.",
         "role_match": "Full Stack Developer", "url": "https://yourstory.com", "date": "2025-03-20"},
        {"name": "Probo", "amount_inr": 280000000, "round_type": "Series A", "sector": "FinTech",
         "score": 79, "confidence": "HIGH", "source": "Google News",
         "summary_what": "Opinion trading platform for real-world events.",
         "summary_why": "Series A = scaling tech infra now.",
         "role_match": "Backend Developer", "url": "https://inc42.com", "date": "2025-03-20"},
        {"name": "Classplus", "amount_inr": 150000000, "round_type": "Series B", "sector": "EdTech",
         "score": 74, "confidence": "MEDIUM", "source": "Entrackr",
         "summary_what": "Creator-led education platform for 50,000+ teachers.",
         "summary_why": "Growing engineering team for product roles.",
         "role_match": "Software Engineer", "url": "https://entrackr.com", "date": "2025-03-20"},
        {"name": "Zypp Electric", "amount_inr": 250000000, "round_type": "Series A", "sector": "Logistics",
         "score": 71, "confidence": "HIGH", "source": "Inc42",
         "summary_what": "India's largest EV two-wheeler fleet for last-mile delivery.",
         "summary_why": "Fleet expansion = IoT and data roles opening.",
         "role_match": "Data Analyst", "url": "https://inc42.com", "date": "2025-03-20"},
    ]


def run_web_app() -> None:
    init_db()
    print("\n" + "=" * 50)
    print("  FundedFirst Dashboard (Firebase + Auth)")
    print(f"  Open: http://localhost:{APP_PORT}")
    print("=" * 50 + "\n")
    app.run(debug=APP_DEBUG, host=APP_HOST, port=APP_PORT)


if __name__ == "__main__":
    run_web_app()
