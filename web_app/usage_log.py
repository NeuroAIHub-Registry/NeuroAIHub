"""Anonymous usage logging to a private Google Sheet (see usage_logging/SETUP.md).

Rows are sent to a Google Apps Script web app attached to the sheet. Logging is off unless LOG_ENDPOINT is set in
Streamlit secrets, and it never blocks or breaks the app: rows are sent in a background thread and errors are ignored.
Never logged: API keys, the full base URL, IP addresses, browser details, names or accounts.
"""
import json
import threading
import uuid
from urllib.parse import urlparse

import requests
import streamlit as st

ANSWER_LIMIT = 2000      # characters kept of each answer (questions are always stored in full)
LOOKUPS_LIMIT = 2000


def _secret(name):
    try:
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:  # no secrets file (e.g. local development)
        return ""


def endpoint() -> str:
    """URL of the logging web app, also handed to the website for browse logging ('' = logging off)."""
    return _secret("LOG_ENDPOINT")


def session_id() -> str:
    if "log_session_id" not in st.session_state:
        st.session_state.log_session_id = uuid.uuid4().hex[:8]
    return st.session_state.log_session_id


def _post(url, payload):
    try:
        requests.post(url, data=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                      headers={"Content-Type": "text/plain; charset=utf-8"}, timeout=20)
    except Exception:
        pass


def _short(text, limit):
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[:limit] + "…"


def log_chat(question, result, model, base_url, turn, seconds):
    url = endpoint()
    if not url:
        return
    lookups = "; ".join(f"{name}{json.dumps(args, ensure_ascii=False, default=str)}" for name, args in result.steps)
    table = result.tables[-1][1] if result.tables else None
    row = {
        "session_id": session_id(),
        "turn": turn,
        "model": model,
        "provider": urlparse(base_url).hostname if base_url else "api.openai.com",
        "question": question,                                   # full text
        "answer": _short(result.text or result.error, ANSWER_LIMIT),
        "lookups": _short(lookups, LOOKUPS_LIMIT),
        "datasets_returned": len(table) if table is not None else "",
        "chart": "yes" if result.images else "no",
        "status": result.status,
        "seconds": round(seconds, 1),
        "model_calls": result.model_calls,
    }
    payload = {"tab": "chat", "token": _secret("LOG_TOKEN"), "row": row}
    threading.Thread(target=_post, args=(url, payload), daemon=True).start()
