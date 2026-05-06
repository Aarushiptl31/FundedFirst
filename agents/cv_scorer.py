from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

import requests

try:
    from google import genai
except Exception:  # pragma: no cover - fallback keeps imports working without package
    genai = None  # type: ignore[assignment]

from config import GEMINI_API_KEY, GEMINI_MODEL, setup_logging


setup_logging()
logger = logging.getLogger(__name__)

MAX_CV_CHARS = 3000
_missing_key_logged = False


def _default_result() -> Dict[str, Any]:
    return {
        "cv_score": 50,
        "grade": "AVERAGE",
        "skills_score": 50,
        "projects_score": 50,
        "academics_score": 50,
        "top_strengths": ["Could not analyse CV"],
        "critical_improvements": [
            {"issue": "CV unreadable", "fix": "Ensure CV is a text-based PDF not a scanned image"}
        ],
        "missing_skills": [],
        "hiring_verdict": "Unable to analyse CV; please check the PDF file.",
    }


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract plain text from a PDF file using PyMuPDF, then PyPDF2 as fallback."""
    try:
        import pymupdf

        doc = pymupdf.open(pdf_path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    except ImportError:
        pass
    except Exception as exc:
        logger.exception("extract_text_from_pdf: PyMuPDF failed for %s: %s", pdf_path, exc)

    try:
        import PyPDF2

        text = ""
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
        return text.strip()
    except Exception as exc:
        logger.exception("extract_text_from_pdf: failed to read %s: %s", pdf_path, exc)
        return ""


def _download_if_url(cv_path: str) -> str:
    """Download CV when cv_path is an HTTP URL and return local temp path."""
    if not cv_path.lower().startswith(("http://", "https://")):
        return cv_path

    parsed = urlparse(cv_path)
    download_url = cv_path
    if "drive.google.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        file_id = query.get("id", [""])[0]
        if not file_id and "/file/d/" in parsed.path:
            parts = parsed.path.split("/file/d/")
            if len(parts) > 1:
                file_id = parts[1].split("/")[0]
        if file_id:
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    resp = requests.get(download_url, timeout=20)
    resp.raise_for_status()
    with tempfile.NamedTemporaryFile(prefix="fundedfirst_cv_", suffix=".pdf", delete=False) as tmp:
        tmp.write(resp.content)
        return tmp.name


def _build_cv_prompt(
    cv_text: str,
    startup_sector: str,
    startup_context: Optional[Dict[str, Any]] = None,
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    """Build CV scoring prompt against startup sector."""
    profile = user_profile or {}
    data = {
        "cv_text": cv_text[:MAX_CV_CHARS],
        "user_profile": {
            "name": profile.get("name", ""),
            "degree": profile.get("degree", ""),
            "cgpa": profile.get("cgpa", ""),
            "year": profile.get("year", ""),
            "skills": profile.get("skills", ""),
            "experience": profile.get("experience", ""),
            "role_target": profile.get("role_target", ""),
            "certificates": profile.get("certificates", ""),
        },
        "target_startup_sector": startup_sector,
        "startup_context": startup_context or {},
        "evaluation_criteria": {
            "skills_match": {"weight": 0.40},
            "projects_and_experience": {"weight": 0.35},
            "academics": {"weight": 0.25},
        },
    }
    instructions = (
        "You are a senior technical recruiter reviewing a fresher's CV for a startup in the given sector. "
        "Evaluate strictly and honestly across skills, projects, and academics. "
        "Be specific: name exact missing skills, weak project descriptions, or academic gaps. "
        "Return JSON exactly: "
        "{"
        '"cv_score": 0, '
        '"grade": "STRONG|GOOD|AVERAGE|WEAK", '
        '"skills_score": 0, '
        '"projects_score": 0, '
        '"academics_score": 0, '
        '"top_strengths": ["strength1", "strength2", "strength3"], '
        '"critical_improvements": [{"issue": "short issue", "fix": "specific fix"}], '
        '"missing_skills": ["skill1", "skill2", "skill3"], '
        '"hiring_verdict": "one honest sentence"'
        "}. "
        "Respond ONLY in valid JSON"
    )
    return json.dumps(data, ensure_ascii=False) + "\n\n" + instructions


def _coerce_score(value: Any, fallback: int = 50) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return fallback


def score_cv(
    cv_path: str,
    startup_sector: str = "General Tech",
    startup_context: Optional[Dict[str, Any]] = None,
    user_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Score a fresher CV PDF against a startup sector using Gemini."""
    default = _default_result()
    global _missing_key_logged
    if not GEMINI_API_KEY or genai is None:
        if not _missing_key_logged:
            logger.warning("score_cv: Gemini API key or google-genai package missing.")
            _missing_key_logged = True
        return default

    local_cv_path = cv_path
    downloaded_temp = False
    try:
        local_cv_path = _download_if_url(cv_path)
        downloaded_temp = local_cv_path != cv_path
        if not os.path.exists(local_cv_path):
            result = dict(default)
            result["hiring_verdict"] = f"CV file not found at: {local_cv_path}"
            return result

        cv_text = extract_text_from_pdf(local_cv_path)
        if not cv_text or len(cv_text.strip()) < 50:
            result = dict(default)
            result["hiring_verdict"] = "CV appears to be a scanned image. Use a text-based PDF."
            return result

        prompt = _build_cv_prompt(
            cv_text,
            startup_sector,
            startup_context=startup_context,
            user_profile=user_profile,
        )
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"max_output_tokens": 500},
        )
        data = json.loads(response.text)
        grade = str(data.get("grade", "AVERAGE")).upper()
        if grade not in {"STRONG", "GOOD", "AVERAGE", "WEAK"}:
            grade = "AVERAGE"
        strengths = data.get("top_strengths", [])
        improvements = data.get("critical_improvements", [])
        missing_skills = data.get("missing_skills", [])
        return {
            "cv_score": _coerce_score(data.get("cv_score")),
            "grade": grade,
            "skills_score": _coerce_score(data.get("skills_score")),
            "projects_score": _coerce_score(data.get("projects_score")),
            "academics_score": _coerce_score(data.get("academics_score")),
            "top_strengths": strengths[:5] if isinstance(strengths, list) else [],
            "critical_improvements": improvements[:6] if isinstance(improvements, list) else [],
            "missing_skills": missing_skills[:8] if isinstance(missing_skills, list) else [],
            "hiring_verdict": str(data.get("hiring_verdict", default["hiring_verdict"]))[:300],
        }
    except Exception as exc:
        logger.exception("score_cv: Gemini error: %s", exc)
        return default
    finally:
        if downloaded_temp:
            try:
                os.unlink(local_cv_path)
            except Exception:
                pass


def print_cv_report(result: Dict[str, Any], startup_name: str = "", sector: str = "") -> None:
    """Print a clean CV feedback report to terminal."""
    grade_marker = {
        "STRONG": "[STRONG]",
        "GOOD": "[GOOD]",
        "AVERAGE": "[AVERAGE]",
        "WEAK": "[WEAK]",
    }.get(result.get("grade", "AVERAGE"), "[AVERAGE]")

    print("\n" + "=" * 60)
    print("  CV ANALYSIS REPORT")
    if startup_name:
        print(f"  For: {startup_name} ({sector})")
    print("=" * 60)
    print(f"\n  Overall CV Score : {result['cv_score']}/100  {grade_marker}")
    print(f"  Skills Match     : {result['skills_score']}/100")
    print(f"  Projects         : {result['projects_score']}/100")
    print(f"  Academics        : {result['academics_score']}/100")

    print("\n  TOP STRENGTHS:")
    for strength in result.get("top_strengths", []):
        print(f"     - {strength}")

    print("\n  CRITICAL IMPROVEMENTS:")
    for item in result.get("critical_improvements", []):
        if isinstance(item, dict):
            print(f"     - {item.get('issue', '')}: {item.get('fix', '')}")
        else:
            print(f"     - {item}")

    print("\n  MISSING SKILLS TO ADD:")
    missing = result.get("missing_skills", [])
    print(f"     {', '.join(missing)}" if missing else "     None identified")

    print("\n  HIRING VERDICT:")
    print(f"     {result.get('hiring_verdict', '')}")
    print("\n" + "=" * 60 + "\n")


__all__ = ["score_cv", "extract_text_from_pdf", "print_cv_report"]
