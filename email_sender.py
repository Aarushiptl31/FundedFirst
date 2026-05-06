from __future__ import annotations

import html
import logging
import os
import re
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable, List, Mapping
from urllib.parse import quote

from config import (
    EMAIL_PASSWORD,
    EMAIL_PORT,
    EMAIL_SMTP,
    EMAIL_USER,
    HIGH_SCORE_THRESHOLD,
    setup_logging,
)
from utils.confidence import get_confidence_badge


setup_logging()
logger = logging.getLogger(__name__)


def _profile_value(user_profile: Mapping[str, object], key: str, default: str = "") -> str:
    """Return a profile field as clean text."""
    value = user_profile.get(key, default)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _minimal_profile(user_profile: Mapping[str, object] | None = None) -> dict:
    """Normalize optional user profile data for email drafting."""
    profile = dict(user_profile or {})
    return {
        "name": _profile_value(profile, "name", "Candidate"),
        "degree": _profile_value(profile, "degree", "Engineering"),
        "cgpa": _profile_value(profile, "cgpa", ""),
        "skills": _profile_value(profile, "skills", "Python, SQL, problem solving"),
        "experience": _profile_value(profile, "experience", "projects and hands-on learning"),
        "github": _profile_value(profile, "github", ""),
        "linkedin": _profile_value(profile, "linkedin", ""),
        "resume_link": _profile_value(profile, "resume_link", ""),
        "role_target": _profile_value(profile, "role_target", "Software Engineer"),
        "notice_period": _profile_value(profile, "notice_period", "Immediately available"),
        "expected_ctc": _profile_value(profile, "expected_ctc", ""),
        "location": _profile_value(profile, "location", "India"),
        "certificates": _profile_value(profile, "certificates", ""),
    }


def _build_base_message(subject: str, recipient_email: str) -> MIMEMultipart:
    """Create a MIME multipart email with common headers."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = recipient_email
    return msg


def _cgpa_line(user_profile: Mapping[str, object]) -> str:
    """Return a CGPA mention based on the provided profile."""
    cgpa_text = _profile_value(user_profile, "cgpa", "")
    try:
        cgpa = float(cgpa_text or 0)
    except ValueError:
        return ""
    if cgpa >= 8.0:
        return f"My CGPA of {cgpa_text} reflects a strong academic foundation."
    if cgpa >= 7.0:
        return f"I have a {cgpa_text} CGPA along with hands-on project experience."
    return ""


def _build_cold_email(
    startup_name: str,
    round_type: str,
    amount_cr: float,
    sector: str,
    role_match: str,
    summary_what: str,
    summary_why: str,
    user_profile: Mapping[str, object] | None = None,
) -> tuple[str, str]:
    """Build personalized cold email subject and body from a user profile dict."""
    profile = _minimal_profile(user_profile)
    name = profile["name"]
    degree = profile["degree"]
    skills = profile["skills"]
    experience = profile["experience"]
    location = profile["location"]
    github = profile["github"]
    linkedin = profile["linkedin"]
    resume = profile["resume_link"]
    role = role_match or profile["role_target"] or "Software Engineer"
    notice = profile["notice_period"]
    ctc = profile["expected_ctc"]
    certs = profile["certificates"]
    amt_str = f"Rs.{amount_cr:.1f} Cr" if amount_cr else "recent"
    round_str = round_type or "funding"
    cgpa_line = _cgpa_line(profile)

    subject = f"Application for {role} - {name} | {degree}"

    links_parts = []
    if github:
        links_parts.append(f"GitHub: {github}")
    if linkedin:
        links_parts.append(f"LinkedIn: {linkedin}")
    if resume:
        links_parts.append(f"Resume: {resume}")
    links_line = " | ".join(links_parts)

    avail_parts = [f"Notice period: {notice}"]
    if ctc:
        avail_parts.append(f"Expected CTC: {ctc}")
    avail_line = " | ".join(avail_parts)

    certs_line = f"Certifications: {certs}" if certs else ""
    what_line = summary_what or (
        f"your work in {sector or 'this space'} is exactly the kind of product I want to build"
    )
    why_line = summary_why or "Fresh funding often means rapid team growth, and I would love to join early."

    optional_lines = "\n".join(line for line in [cgpa_line, certs_line] if line)
    links_block = f"\n{links_line}" if links_line else ""

    body = f"""Dear Hiring Team at {startup_name},

I came across {startup_name}'s {amt_str} {round_str} and was genuinely excited - {what_line}

{why_line}

I am {name}, a {degree} student/graduate from {location}. My core skills include {skills}, and I have experience through {experience}.
{optional_lines}
I am actively looking for a {role} role and believe my background is a strong fit for what {startup_name} is building right now.
{links_block}
{avail_line}

I would love the opportunity for a quick 15-minute call. Looking forward to hearing from you.

Best regards,
{name}"""

    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return subject, body


def _make_mailto(
    startup_name: str,
    subject: str,
    body: str,
    user_profile: Mapping[str, object] | None = None,
) -> str:
    """Build mailto link that opens an email client with a pre-filled cold email."""
    safe = re.sub(r"[^a-z0-9-]", "", startup_name.lower().replace(" ", ""))
    to_email = _profile_value(user_profile or {}, "contact_email", "")
    if not to_email:
        to_email = f"hiring@{safe or 'startup'}.com"
    return f"mailto:{quote(to_email)}?subject={quote(subject)}&body={quote(body)}"


def build_digest_html(
    startups: List[Mapping[str, object]],
    user_profile: Mapping[str, object] | None = None,
) -> str:
    """Build responsive HTML digest for all startups sorted by score."""
    profile = _minimal_profile(user_profile)
    cards: List[str] = []
    for s in sorted(startups, key=lambda x: int(x.get("score", 0) or 0), reverse=True):
        score = int(s.get("score", 0) or 0)
        confidence = str(s.get("confidence") or "MEDIUM")
        badge = get_confidence_badge(confidence)
        name = str(s.get("name") or "Unknown Startup")
        amount = s.get("amount_inr") or 0
        round_type = str(s.get("round_type") or "")
        sector = str(s.get("sector") or "")
        summary_what = str(s.get("summary_what") or "")
        summary_why = str(s.get("summary_why") or "")
        role_match = str(s.get("role_match") or profile["role_target"] or "Software Engineer")
        url = str(s.get("url") or "#")
        source = str(s.get("source") or "")

        score_color = "#16a34a" if score >= HIGH_SCORE_THRESHOLD else "#f97316"
        amount_cr = float(amount) / 10_000_000 if amount else 0.0

        email_subject, email_body = _build_cold_email(
            startup_name=name,
            round_type=round_type,
            amount_cr=amount_cr,
            sector=sector,
            role_match=role_match,
            summary_what=summary_what,
            summary_why=summary_why,
            user_profile=profile,
        )
        mailto_link = _make_mailto(name, email_subject, email_body, profile)

        card_html = f"""
        <tr>
          <td style="padding:16px 0;">
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border-radius:12px;border:1px solid #e5e7eb;
                          background:#ffffff;padding:16px;">
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="font-size:18px;font-weight:600;color:#111827;">{html.escape(name)}</td>
                      <td align="right">
                        <span style="font-size:13px;font-weight:600;color:{score_color};
                                     padding:4px 10px;border-radius:999px;
                                     border:1px solid {score_color};">
                          Score: {score}/100
                        </span>
                      </td>
                    </tr>
                  </table>
                  <div style="margin:8px 0;font-size:13px;">
                    <span style="display:inline-block;padding:3px 8px;border-radius:999px;
                                 background:#eff6ff;color:#1d4ed8;margin-right:4px;">
                      &#8377;{amount_cr:.1f} Cr
                    </span>
                    <span style="display:inline-block;padding:3px 8px;border-radius:999px;
                                 background:#ecfdf5;color:#15803d;margin-right:4px;">
                      {html.escape(round_type or "Funding")}
                    </span>
                    <span style="display:inline-block;padding:3px 8px;border-radius:999px;
                                 background:#fef3c7;color:#92400e;margin-right:4px;">
                      {html.escape(sector or "General")}
                    </span>
                    <span style="display:inline-block;padding:3px 8px;border-radius:999px;
                                 background:#f3f4f6;color:#6b7280;">
                      {html.escape(source)}
                    </span>
                  </div>
                  <div style="margin-bottom:6px;font-size:12px;">{html.escape(badge)}</div>
                  <div style="margin-bottom:4px;font-size:14px;color:#111827;">{html.escape(summary_what)}</div>
                  <div style="margin-bottom:8px;font-size:13px;color:#4b5563;">{html.escape(summary_why)}</div>
                  <div style="margin-bottom:12px;font-size:13px;color:#1f2933;">
                    Best match for you: <strong>{html.escape(role_match)}</strong>
                  </div>
                  <div>
                    <a href="{html.escape(url, quote=True)}"
                       style="text-decoration:none;padding:8px 14px;border-radius:999px;
                              background:#111827;color:#ffffff;font-size:13px;margin-right:8px;">
                      Read More
                    </a>
                    <a href="{html.escape(mailto_link, quote=True)}"
                       style="text-decoration:none;padding:8px 14px;border-radius:999px;
                              background:#0071e3;color:#ffffff;font-size:13px;font-weight:600;">
                      &#9993;&nbsp;Apply Now
                    </a>
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """
        cards.append(card_html)

    if not cards:
        return ""

    return f"""
    <html>
      <body style="background:#f3f4f6;margin:0;padding:0;
                   font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0;">
          <tr><td align="center">
            <table width="600" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#0f172a;border-radius:12px 12px 0 0;padding:20px 24px;">
                  <div style="font-size:22px;font-weight:700;color:#ffffff;">&#128640; FundedFirst</div>
                  <div style="font-size:13px;color:#94a3b8;margin-top:4px;">
                    Newly funded Indian startups - apply before jobs hit LinkedIn
                  </div>
                </td>
              </tr>
              <tr>
                <td style="background:#f9fafb;padding:0 16px 16px 16px;border-radius:0 0 12px 12px;">
                  <table width="100%" cellpadding="0" cellspacing="0">{"".join(cards)}</table>
                </td>
              </tr>
              <tr>
                <td style="padding:16px;text-align:center;font-size:12px;color:#9ca3af;">
                  FundedFirst by TantraGyan - Information asymmetry khatam karo.
                </td>
              </tr>
            </table>
          </td></tr>
        </table>
      </body>
    </html>
    """


def build_digest_plain(
    startups: List[Mapping[str, object]],
    user_profile: Mapping[str, object] | None = None,
) -> str:
    """Build plain text digest including cold email draft per startup."""
    profile = _minimal_profile(user_profile)
    lines: List[str] = []
    for s in sorted(startups, key=lambda x: int(x.get("score", 0) or 0), reverse=True):
        score = int(s.get("score", 0) or 0)
        name = str(s.get("name") or "Unknown")
        amount = s.get("amount_inr") or 0
        round_type = str(s.get("round_type") or "")
        sector = str(s.get("sector") or "")
        summary_what = str(s.get("summary_what") or "")
        summary_why = str(s.get("summary_why") or "")
        role_match = str(s.get("role_match") or profile["role_target"] or "Generalist")
        url = str(s.get("url") or "#")
        confidence = str(s.get("confidence") or "MEDIUM")
        amount_cr = float(amount) / 10_000_000 if amount else 0.0

        email_subject, email_body = _build_cold_email(
            startup_name=name,
            round_type=round_type,
            amount_cr=amount_cr,
            sector=sector,
            role_match=role_match,
            summary_what=summary_what,
            summary_why=summary_why,
            user_profile=profile,
        )

        lines.append(f"{name} - Score {score}/100 ({confidence})")
        lines.append(f"Rs.{amount_cr:.1f} Cr | {round_type or 'Funding'} | {sector or 'General'}")
        if summary_what:
            lines.append(summary_what)
        if summary_why:
            lines.append(summary_why)
        lines.append(f"Best role match: {role_match}")
        lines.append(f"Read more: {url}")
        lines.append("--- COLD EMAIL DRAFT ---")
        lines.append(f"Subject: {email_subject}")
        lines.append(email_body)
        lines.append("-" * 60)
    return "\n".join(lines) if lines else ""


def _send_message(msg: MIMEMultipart, recipient_email: str) -> bool:
    """Send a MIME email using SMTP and TLS."""
    if not EMAIL_USER or not EMAIL_PASSWORD or not recipient_email:
        logger.error("send_message: email credentials or recipient not configured")
        return False
    try:
        verify_tls = os.getenv("EMAIL_SSL_VERIFY", "true").lower() not in {"0", "false", "no"}
        contexts = [ssl.create_default_context()]
        if not verify_tls:
            contexts = [ssl._create_unverified_context()]
        for attempt, context in enumerate(contexts, start=1):
            try:
                with smtplib.SMTP(EMAIL_SMTP, EMAIL_PORT) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(EMAIL_USER, EMAIL_PASSWORD)
                    server.send_message(msg)
                logger.info("send_message: email sent to %s", recipient_email)
                return True
            except ssl.SSLCertVerificationError as exc:
                if not verify_tls:
                    raise
                logger.warning(
                    "send_message: TLS cert verification failed attempt %s: %s. Retrying.",
                    attempt,
                    exc,
                )
                contexts.append(ssl._create_unverified_context())
            except Exception:
                raise
    except Exception as exc:
        logger.exception("send_message: error sending email: %s", exc)
        return False


def send_email(
    startups: Iterable[Mapping[str, object]],
    recipient_email: str = "",
    user_profile: dict | None = None,
) -> bool:
    """Send the daily digest email for startups."""
    if not recipient_email:
        logger.info("send_email: recipient email empty; skipping digest send")
        return False
    try:
        startup_list = list(startups)
        if not startup_list:
            logger.info("send_email: no startups to send in digest")
            return False
        html_body = build_digest_html(startup_list, user_profile=user_profile)
        plain_body = build_digest_plain(startup_list, user_profile=user_profile)
        if not html_body and not plain_body:
            logger.info("send_email: digest builders returned empty content")
            return False
        subject = f"FundedFirst - {len(startup_list)} funded startup(s) today!"
        msg = _build_base_message(subject, recipient_email)
        if plain_body:
            msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        return _send_message(msg, recipient_email)
    except Exception as exc:
        logger.exception("send_email: error building or sending digest: %s", exc)
        return False


def send_alert_email(subject: str, body: str) -> bool:
    """Send an alert email for failures or important notifications."""
    recipient_email = EMAIL_USER
    try:
        msg = _build_base_message(subject, recipient_email)
        msg.attach(MIMEText(body, "plain", "utf-8"))
        return _send_message(msg, recipient_email)
    except Exception as exc:
        logger.exception("send_alert_email: error: %s", exc)
        return False


def send_with_attachment(subject: str, body: str, csv_bytes: bytes, filename: str) -> bool:
    """Send an email with a CSV attachment to the configured sender mailbox."""
    recipient_email = EMAIL_USER
    try:
        msg = _build_base_message(subject, recipient_email)
        msg.attach(MIMEText(body, "plain", "utf-8"))
        part = MIMEApplication(csv_bytes, Name=filename)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        msg.attach(part)
        return _send_message(msg, recipient_email)
    except Exception as exc:
        logger.exception("send_with_attachment: error: %s", exc)
        return False


__all__ = [
    "build_digest_html",
    "build_digest_plain",
    "send_email",
    "send_alert_email",
    "send_with_attachment",
]
