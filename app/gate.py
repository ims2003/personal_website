"""Tiny email-code gate for the reflections pages. A speed bump, not real security."""
import hashlib
import json
import os
import re
import secrets
import time
import urllib.request
from datetime import timedelta

from flask import redirect, render_template_string, request, session

PREFIX = "/reflections/"  # change to match your reflections URLs
CODE_MINUTES = 10
ALLOWED = {e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()}

PAGE = """<!doctype html>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reflections</title>
<body style="font-family:system-ui,sans-serif;max-width:360px;margin:15vh auto;padding:0 16px">
  <h1>Reflections</h1>
  {% if email %}
    <p>A 6-digit code was sent to {{ email }}. It expires in {{ minutes }} minutes.</p>
    <form method="post" action="/gate/verify">
      <input type="hidden" name="next" value="{{ next }}">
      <input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required autofocus
             placeholder="123456" style="width:100%;padding:10px;font:inherit;box-sizing:border-box">
      <button style="margin-top:10px;padding:10px 16px;font:inherit">Continue</button>
    </form>
    <form method="post" action="/gate/reset"><input type="hidden" name="next" value="{{ next }}">
      <button style="margin-top:8px;background:none;border:none;padding:0;text-decoration:underline;font:inherit;cursor:pointer">Use a different email</button>
    </form>
  {% else %}
    <p>Enter your email and you'll be sent a code to continue.</p>
    <form method="post" action="/gate/send">
      <input type="hidden" name="next" value="{{ next }}">
      <input type="email" name="email" required autofocus placeholder="you@example.com"
             style="width:100%;padding:10px;font:inherit;box-sizing:border-box">
      <button style="margin-top:10px;padding:10px 16px;font:inherit">Send code</button>
    </form>
  {% endif %}
  {% if error %}<p style="color:#c0392b">{{ error }}</p>{% endif %}
</body>"""


def _is_gated(path):
    return path == PREFIX or path.startswith(PREFIX + "/")


def _next():
    nxt = request.form.get("next", PREFIX)
    return nxt if _is_gated(nxt) else PREFIX


def _page(next, error=None, status=200):
    pending = session.get("pending")
    email = pending["email"] if pending and pending["exp"] > time.time() else None
    return render_template_string(PAGE, next=next, email=email, minutes=CODE_MINUTES, error=error), status


def _hash(email, code):
    return hashlib.sha256(f"{os.environ.get('GATE_SECRET', '')}:{email}:{code}".encode()).hexdigest()


def _send_code(email, code):
    """Sends the code via Resend and BCCs you, which doubles as your log."""
    msg = {
        "from": os.environ.get("GATE_FROM"),
        "to": [email],
        "subject": "Your access code",
        "text": f"Your code is {code}. It expires in {CODE_MINUTES} minutes.",
    }
    if os.environ.get("OWNER_EMAIL"):
        msg["bcc"] = [os.environ["OWNER_EMAIL"]]
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(msg).encode(),
        headers={
            "Authorization": f"Bearer {os.environ.get('RESEND_API_KEY', '')}",
            "Content-Type": "application/json",
            "User-Agent": "reflections-gate",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except Exception as exc:
        print(f"[gate] send to {email} failed: {exc}")
        return False


def init_gate(app):
    app.secret_key = app.secret_key or os.environ.get("GATE_SECRET", "change-me")
    app.permanent_session_lifetime = timedelta(days=30)

    @app.before_request
    def gate():
        if _is_gated(request.path) and not session.get("reader"):
            return _page(request.path)

    @app.route("/gate/send", methods=["POST"])
    def gate_send():
        email = request.form.get("email", "").strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            return _page(_next(), "Enter a valid email address.", 400)
        if ALLOWED and email not in ALLOWED:
            print(f"[gate] denied: {email}")
            return _page(_next(), "That email doesn't have access.", 403)

        code = f"{secrets.randbelow(1_000_000):06d}"
        if not _send_code(email, code):
            return _page(_next(), "The code couldn't be sent. Try again.", 502)
        session["pending"] = {"email": email, "h": _hash(email, code), "exp": time.time() + CODE_MINUTES * 60}
        return _page(_next())

    @app.route("/gate/verify", methods=["POST"])
    def gate_verify():
        pending = session.get("pending")
        if not pending or pending["exp"] < time.time():
            session.pop("pending", None)
            return _page(_next(), "That code expired. Request a new one.", 400)
        if not secrets.compare_digest(_hash(pending["email"], request.form.get("code", "").strip()), pending["h"]):
            return _page(_next(), "That code doesn't match.", 400)

        session.pop("pending", None)
        session.permanent = True
        session["reader"] = pending["email"]
        print(f"[gate] entered: {pending['email']}")
        return redirect(_next())

    @app.route("/gate/reset", methods=["POST"])
    def gate_reset():
        session.pop("pending", None)
        return redirect(_next())
