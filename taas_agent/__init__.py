"""ADK agent package for the Terraform-as-a-Service proof of concept."""

import os
import shutil
import subprocess
from pathlib import Path

# Load .env file from project root if it exists
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILE = _PROJECT_ROOT / ".env"

if _ENV_FILE.is_file():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_FILE)
    except ImportError:
        # Fallback simple parser if python-dotenv isn't installed yet
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# When in GCP / Cloud Shell without a direct Gemini API key, use Vertex AI
if not os.getenv("GEMINI_API_KEY"):
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")

# Auto-detect project ID from gcloud if not explicitly set
if not os.getenv("GOOGLE_CLOUD_PROJECT"):
    gcloud_bin = shutil.which("gcloud")
    if gcloud_bin:
        try:
            detected_project = subprocess.check_output(
                [gcloud_bin, "config", "get-value", "project"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).strip()
            if detected_project and detected_project != "(unset)":
                os.environ["GOOGLE_CLOUD_PROJECT"] = detected_project
        except Exception:
            pass

os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("TAAS_STATE_BUCKET", "terraform-implementation")
os.environ.setdefault("TAAS_MODEL", "gemini-3.5-flash-lite")

# Automatically verify and install/symlink Terraform on startup
try:
    from .tools.tools import ensure_terraform_binary
    ensure_terraform_binary()
except Exception:
    pass
