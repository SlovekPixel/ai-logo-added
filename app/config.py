from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
STATE_FILE = DATA_DIR / "state.json"
JOBS_DIR = DATA_DIR / "jobs"

ACCESS_CODE = os.getenv("ACCESS_CODE", "")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

MAX_FILES = int(os.getenv("MAX_FILES", "200"))
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "10"))
MAX_TOTAL_MB = int(os.getenv("MAX_TOTAL_MB", "300"))
ZIP_TTL_MINUTES = int(os.getenv("ZIP_TTL_MINUTES", "20"))

MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
MAX_TOTAL_BYTES = MAX_TOTAL_MB * 1024 * 1024

SESSION_COOKIE = "logo_session"
SESSION_MAX_AGE = 60 * 60 * 12  # 12 hours
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/jpg",
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
