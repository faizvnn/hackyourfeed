"""Environment config. Copy .env.example to .env and fill in keys."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
PROMPTS = ROOT / "app" / "prompts"
WORK_DIR = Path(os.getenv("WORK_DIR", ROOT / "work"))
RENDER_DIR = WORK_DIR / "renders"

# Stage names listed here return their fixture instead of doing real work,
# e.g. USE_FIXTURES=ingest,trends lets you build stage 2 without yt-dlp or an Oriane key.
USE_FIXTURES: set[str] = {s.strip() for s in os.getenv("USE_FIXTURES", "").split(",") if s.strip()}

# GMI Cloud inference (OpenAI-compatible)
GMI_BASE_URL = os.getenv("GMI_BASE_URL", "https://api.gmi-serving.com/v1")
GMI_API_KEY = os.getenv("GMI_API_KEY", "")
GMI_MODEL = os.getenv("GMI_MODEL", "")

# Oriane
ORIANE_BASE_URL = os.getenv("ORIANE_BASE_URL", "https://connect.oriane.xyz")
ORIANE_API_KEY = os.getenv("ORIANE_API_KEY", "")
ORIANE_AUTH_HEADER = os.getenv("ORIANE_AUTH_HEADER", "Authorization")  # verified: "Authorization: Bearer <key>"

# Compound.mov
COMPOUND_API_KEY = os.getenv("COMPOUND_API_KEY", "")

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")


def use_fixture(stage: str) -> bool:
    return stage in USE_FIXTURES or "all" in USE_FIXTURES
