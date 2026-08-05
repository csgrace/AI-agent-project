"""Credentials Settings API — runtime CAS / Todoist credential management.

Endpoints
---------
- ``GET  /api/settings/credentials/status`` — current credential status (masked)
- ``POST /api/settings/credentials`` — set new credentials, persist to credential files
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter

from pydantic import BaseModel

router = APIRouter(prefix="/api/settings/credentials", tags=["credentials"])

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[3]
CREDENTIALS_DIR = BACKEND_ROOT / "credentials"
PROFILE_PATH = CREDENTIALS_DIR / "profile.json"
TODOIST_CREDENTIALS_PATH = CREDENTIALS_DIR / "todoist_credentials.json"
COOKIES_PATH = CREDENTIALS_DIR / "cookies.json"


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class CredentialSetConfigRequest(BaseModel):
    cas_username: Optional[str] = None
    cas_password: Optional[str] = None
    todoist_token: Optional[str] = None


class CredentialStatusResponse(BaseModel):
    cas_configured: bool = False
    cas_username_masked: str = ""
    todoist_configured: bool = False
    todoist_token_masked: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask(value: Optional[str], keep_front: int = 4, keep_back: int = 4) -> str:
    """Return a masked version of a secret string, e.g. ``"1234****5678"``."""
    if not value:
        return ""
    total = len(value)
    if total <= keep_front + keep_back + 2:
        # very short string – show first and last char
        if total <= 2:
            return value[0] + "*" if total > 1 else value
        return value[:keep_front] + "****" + value[-keep_back:]
    return value[:keep_front] + "****" + value[-keep_back:]


def _read_json(path: Path) -> dict:
    """Read a JSON file, returning empty dict on error."""
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _write_json(path: Path, data: dict) -> None:
    """Write a JSON file, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_cas_profile() -> tuple[str, str]:
    """Load CAS username and password from profile.json."""
    data = _read_json(PROFILE_PATH)
    return data.get("username", ""), data.get("password", "")


def _load_todoist_token() -> str:
    """Load Todoist access token from todoist_credentials.json."""
    data = _read_json(TODOIST_CREDENTIALS_PATH)
    return data.get("access_token", "")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=CredentialStatusResponse)
async def get_credential_status():
    """Return a summary of the current credential configuration (masked)."""
    cas_user, cas_pass = _load_cas_profile()
    todoist_token = _load_todoist_token()

    return CredentialStatusResponse(
        cas_configured=bool(cas_user and cas_pass),
        cas_username_masked=_mask(cas_user),
        todoist_configured=bool(todoist_token),
        todoist_token_masked=_mask(todoist_token),
    )


@router.post("", response_model=CredentialStatusResponse)
async def set_credentials(req: CredentialSetConfigRequest):
    """Set credentials and persist to credential files.

    - If ``cas_username`` or ``cas_password`` is provided, updates
      ``credentials/profile.json``.
    - If ``todoist_token`` is provided, updates
      ``credentials/todoist_credentials.json``.
    - When CAS password changes, clears cached cookies at
      ``credentials/cookies.json``.
    """
    cas_user_before, cas_pass_before = _load_cas_profile()

    # ── CAS credentials ──────────────────────────────────────────────
    if req.cas_username is not None or req.cas_password is not None:
        new_user = req.cas_username if req.cas_username is not None else cas_user_before
        new_pass = req.cas_password if req.cas_password is not None else cas_pass_before

        profile = {"username": new_user, "password": new_pass}
        _write_json(PROFILE_PATH, profile)

        # Clear cookies if password actually changed
        if req.cas_password is not None and req.cas_password != cas_pass_before:
            try:
                if COOKIES_PATH.exists():
                    COOKIES_PATH.unlink()
                    print("[credentials] CAS password changed — cleared cookies cache.")
            except OSError as e:
                print(f"[credentials] Warning: could not clear cookies: {e}")

    # ── Todoist token ────────────────────────────────────────────────
    if req.todoist_token is not None:
        token_data = {"access_token": req.todoist_token, "token_type": "Bearer"}
        _write_json(TODOIST_CREDENTIALS_PATH, token_data)

    return await get_credential_status()
