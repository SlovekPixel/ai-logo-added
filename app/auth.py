from __future__ import annotations

import json
import secrets
from datetime import date
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import (
    ACCESS_CODE,
    SECRET_KEY,
    SESSION_MAX_AGE,
    STATE_FILE,
    ensure_dirs,
)

MAX_FAILS = 5


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(SECRET_KEY, salt="logo-session")


def create_session_token() -> str:
    return _serializer().dumps({"ok": True, "nonce": secrets.token_hex(8)})


def verify_session_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
        return bool(data.get("ok"))
    except (BadSignature, SignatureExpired):
        return False


def _default_state() -> dict[str, Any]:
    return {
        "day": date.today().isoformat(),
        "fail_count": 0,
        "locked": False,
    }


def load_state() -> dict[str, Any]:
    ensure_dirs()
    if not STATE_FILE.exists():
        state = _default_state()
        save_state(state)
        return state

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        state = _default_state()
        save_state(state)
        return state

    today = date.today().isoformat()
    # Reset daily fail counter only when not locked
    if state.get("day") != today and not state.get("locked"):
        state["day"] = today
        state["fail_count"] = 0
        save_state(state)
    elif state.get("day") != today and state.get("locked"):
        # Keep locked; update day so we don't repeatedly rewrite
        state["day"] = today
        save_state(state)

    return state


def save_state(state: dict[str, Any]) -> None:
    ensure_dirs()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def is_locked() -> bool:
    return bool(load_state().get("locked"))


def unlock() -> None:
    state = _default_state()
    state["locked"] = False
    state["fail_count"] = 0
    save_state(state)


def validate_access_code_config() -> str | None:
    if len(ACCESS_CODE) != 30:
        return (
            f"ACCESS_CODE must be exactly 30 characters "
            f"(currently {len(ACCESS_CODE)})."
        )
    return None


def attempt_login(code: str) -> dict[str, Any]:
    """Try login. Returns dict with ok, locked, remaining, message, token?"""
    state = load_state()

    if state.get("locked"):
        return {
            "ok": False,
            "locked": True,
            "remaining": 0,
            "message": "Сайт заблокирован. Обратитесь к администратору.",
        }

    cfg_err = validate_access_code_config()
    if cfg_err:
        return {
            "ok": False,
            "locked": False,
            "remaining": MAX_FAILS - int(state.get("fail_count", 0)),
            "message": "Сервер не настроен: неверный ACCESS_CODE в .env",
        }

    if len(code) != len(ACCESS_CODE) or not secrets.compare_digest(code, ACCESS_CODE):
        # Wrong code (length mismatch also counts as failure)
        fail_count = int(state.get("fail_count", 0)) + 1
        state["fail_count"] = fail_count
        state["day"] = date.today().isoformat()

        if fail_count >= MAX_FAILS:
            state["locked"] = True
            save_state(state)
            return {
                "ok": False,
                "locked": True,
                "remaining": 0,
                "message": "Сайт заблокирован после 5 неверных попыток.",
            }

        save_state(state)
        remaining = MAX_FAILS - fail_count
        return {
            "ok": False,
            "locked": False,
            "remaining": remaining,
            "message": f"Неверный код. Осталось попыток сегодня: {remaining}",
        }

    return {
        "ok": True,
        "locked": False,
        "remaining": MAX_FAILS - int(state.get("fail_count", 0)),
        "message": "OK",
        "token": create_session_token(),
    }
