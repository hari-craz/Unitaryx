"""Standalone email builders and async delivery helpers.

This module keeps mail composition testable without importing the full Flask app.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "emails"

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        "welcome_subject": "Welcome to Unitary X",
        "welcome_greeting": "Hello {name},",
        "welcome_intro": "Welcome to Unitary X! We're glad you're here.",
        "welcome_body": "You can sign in using your email and password.",
        "welcome_cta": "Go to your dashboard",
        "assigned_subject": "New admin task assigned: {title}",
        "assigned_greeting": "Hello,",
        "assigned_intro": "You have been assigned a new admin task by {assigned_by}.",
        "assigned_body": "Please review the task details below.",
        "assigned_cta": "Open the admin panel",
        "newsletter_confirm_subject": "Confirm your subscription to Unitary X",
        "newsletter_confirm_greeting": "Hello,",
        "newsletter_confirm_intro": "Please confirm that you would like to receive occasional updates from Unitary X.",
        "newsletter_confirm_body": "If you did not request this, ignore this email and you will not be subscribed.",
        "newsletter_confirm_cta": "Confirm subscription",
    },
    "hi": {
        "welcome_subject": "Unitary X में आपका स्वागत है",
        "welcome_greeting": "नमस्ते {name},",
        "welcome_intro": "Unitary X में आपका स्वागत है! हमें खुशी है कि आप जुड़े हैं।",
        "welcome_body": "आप अपने ईमेल और पासवर्ड से साइन इन कर सकते हैं।",
        "welcome_cta": "अपने डैशबोर्ड पर जाएं",
        "assigned_subject": "नया एडमिन कार्य सौंपा गया: {title}",
        "assigned_greeting": "नमस्ते,",
        "assigned_intro": "आपको {assigned_by} द्वारा एक नया एडमिन कार्य सौंपा गया है।",
        "assigned_body": "कृपया नीचे दिए गए कार्य विवरण देखें।",
        "assigned_cta": "एडमिन पैनल खोलें",
        "newsletter_confirm_subject": "Unitary X की सदस्यता की पुष्टि करें",
        "newsletter_confirm_greeting": "नमस्ते,",
        "newsletter_confirm_intro": "कृपया पुष्टि करें कि आप Unitary X से समय-समय पर अपडेट प्राप्त करना चाहते हैं।",
        "newsletter_confirm_body": "यदि आपने यह अनुरोध नहीं किया है, तो इस ईमेल को अनदेखा करें; आपको सदस्यता नहीं दी जाएगी।",
        "newsletter_confirm_cta": "सदस्यता की पुष्टि करें",
    },
}


def _locale_key(locale: str | None) -> str:
    normalized = (locale or "en").strip().lower().replace("_", "-")
    short = normalized.split("-")[0]
    return short if short in TRANSLATIONS else "en"


def _copy(locale: str | None) -> Dict[str, str]:
    return TRANSLATIONS[_locale_key(locale)]


def _render_template(template_name: str, context: Dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    return env.get_template(template_name).render(**context)


def build_welcome_payload(name: str, locale: str | None = None, app_url: str | None = None) -> Tuple[str, str, str]:
    text = _copy(locale)
    subject = text["welcome_subject"]
    context = {
        "name": name,
        "greeting": text["welcome_greeting"].format(name=name),
        "intro": text["welcome_intro"],
        "body": text["welcome_body"],
        "app_url": app_url or os.getenv("APP_URL", ""),
        "cta": text["welcome_cta"],
    }
    plain = _render_template("welcome.txt", context)
    html = _render_template("welcome.html", context)
    return subject, plain, html


def build_assigned_payload(
    title: str,
    details: str,
    assigned_by: str,
    locale: str | None = None,
    app_url: str | None = None,
) -> Tuple[str, str, str]:
    text = _copy(locale)
    subject = text["assigned_subject"].format(title=title)
    context = {
        "title": title,
        "details": details,
        "assigned_by": assigned_by,
        "greeting": text["assigned_greeting"],
        "intro": text["assigned_intro"].format(assigned_by=assigned_by),
        "body": text["assigned_body"],
        "app_url": app_url or os.getenv("APP_URL", ""),
        "cta": text["assigned_cta"],
    }
    plain = _render_template("assigned.txt", context)
    html = _render_template("assigned.html", context)
    return subject, plain, html


def _deliver(
    subject: str, sender: str, recipient: str, plain: str, html: str | None = None, sync: bool = False
) -> None:
    from .email_tasks import send_email

    # send_email is a Celery task when a broker is configured; otherwise a plain
    # sync function. Prefer async delivery, but if enqueuing fails (broker/Redis
    # unreachable — common in local dev, and possible in prod if the worker is
    # down) fall back to sending synchronously in-process. Calling the Celery
    # task object directly runs its body now, so mail still goes out either way.
    # sync=True skips the queue so the caller sees SMTP errors (a queued task
    # that later fails in the worker is invisible to the request that made it).
    enqueue = None if sync else getattr(send_email, "delay", None)
    if callable(enqueue):
        try:
            enqueue(subject, sender, recipient, plain, html)
            return
        except Exception:
            pass
    send_email(subject, sender, recipient, plain, html)


def send_welcome_email(recipient: str, name: str, sender: str, locale: str | None = None, app_url: str | None = None) -> None:
    subject, plain, html = build_welcome_payload(name=name, locale=locale, app_url=app_url)
    _deliver(subject, sender, recipient, plain, html)


def send_assigned_email(
    recipient: str,
    title: str,
    details: str,
    assigned_by: str,
    sender: str,
    locale: str | None = None,
    app_url: str | None = None,
) -> None:
    subject, plain, html = build_assigned_payload(
        title=title,
        details=details,
        assigned_by=assigned_by,
        locale=locale,
        app_url=app_url,
    )
    _deliver(subject, sender, recipient, plain, html)


def build_newsletter_confirm_payload(confirm_url: str, locale: str | None = None) -> Tuple[str, str, str]:
    text = _copy(locale)
    subject = text["newsletter_confirm_subject"]
    context = {
        "greeting": text["newsletter_confirm_greeting"],
        "intro": text["newsletter_confirm_intro"],
        "body": text["newsletter_confirm_body"],
        "confirm_url": confirm_url,
        "cta": text["newsletter_confirm_cta"],
    }
    plain = _render_template("newsletter_confirm.txt", context)
    html = _render_template("newsletter_confirm.html", context)
    return subject, plain, html


def send_newsletter_confirm_email(recipient: str, confirm_url: str, sender: str, locale: str | None = None) -> None:
    subject, plain, html = build_newsletter_confirm_payload(confirm_url=confirm_url, locale=locale)
    # Synchronous on purpose: the subscribe endpoint releases its resend cooldown
    # if delivery fails, which only works if the failure reaches the request.
    _deliver(subject, sender, recipient, plain, html, sync=True)
