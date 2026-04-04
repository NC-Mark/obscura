"""
Dependency bootstrap for PII Shield.

Checks that required packages are installed and downloads AI models.
This runs once at startup. For a clean experience, run setup_pii_shield.py
before first use — this avoids pip installs during a live session.
"""

import subprocess
import sys
import threading
import logging
import time
import json
from pathlib import Path

log = logging.getLogger("pii-shield.bootstrap")

_PACKAGES = [
    ("mcp",                 "mcp[cli]>=1.0.0"),
    ("presidio_analyzer",   "presidio-analyzer>=2.2.355"),
    ("spacy",               "spacy>=3.7.0"),
    ("docx",                "python-docx>=1.1.0"),
    ("numpy",               "numpy>=1.24.0"),
    ("torch",               "torch>=2.0.0"),
    ("gliner",              "gliner>=0.2.7"),
    ("pdfplumber",          "pdfplumber>=0.10.0"),
    ("fastapi",             "fastapi>=0.110.0"),
    ("uvicorn",             "uvicorn>=0.29.0"),
]

# Bootstrap state — readable by tools/API to report progress
state = {
    "phase": "starting",   # starting | packages | models | engine | ready | error
    "message": "",
    "progress_pct": 0,
    "done": False,
    "error": None,
    "start_time": None,
}


def _write_status_file():
    from .config import STATUS_FILE, STATUS_DIR
    try:
        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps({
            "phase": state["phase"],
            "message": state["message"],
            "progress_pct": state["progress_pct"],
            "elapsed_seconds": round(time.time() - state["start_time"], 1) if state["start_time"] else 0,
            "timestamp": time.time(),
        }, indent=2), encoding="utf-8")
    except Exception:
        pass


def _pip_install(specs: list[str]):
    """Install pip packages quietly, detached from parent stdio."""
    from .config import AUDIT_DIR
    log_path = AUDIT_DIR.parent / "pip_install.log"
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW
    with open(log_path, "a") as lf:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + specs,
            stdin=subprocess.DEVNULL, stdout=lf, stderr=lf,
            creationflags=flags,
        )


def install_missing(packages=None) -> list[str]:
    """Check and install missing packages. Returns list of installed specs."""
    packages = packages or _PACKAGES
    missing = []
    for import_name, pip_spec in packages:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_spec)
    if missing:
        log.info(f"Installing missing packages: {missing}")
        _pip_install(missing)
    return missing


def download_models():
    """Download SpaCy tokenizer and GLiNER NER model if not cached."""
    import os
    from .config import GLINER_MODEL

    # SpaCy
    try:
        import spacy
        try:
            spacy.load("en_core_web_sm")
        except OSError:
            log.info("Downloading SpaCy en_core_web_sm...")
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            from .config import AUDIT_DIR
            with open(AUDIT_DIR.parent / "pip_install.log", "a") as lf:
                subprocess.check_call(
                    [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
                    stdin=subprocess.DEVNULL, stdout=lf, stderr=lf,
                    creationflags=flags,
                )
    except Exception as e:
        log.warning(f"SpaCy model download failed: {e}")

    # GLiNER
    try:
        model_name = os.environ.get("PII_GLINER_MODEL", GLINER_MODEL)
        log.info(f"Checking GLiNER model {model_name}...")
        from gliner import GLiNER
        for attempt, delay in enumerate([0, 10, 30, 60]):
            if delay:
                log.info(f"GLiNER retry {attempt} in {delay}s...")
                time.sleep(delay)
            try:
                GLiNER.from_pretrained(model_name)
                log.info(f"GLiNER model ready: {model_name}")
                break
            except Exception as e:
                log.warning(f"GLiNER download attempt {attempt + 1} failed: {e}")
                if attempt == 3:
                    raise
    except Exception as e:
        log.warning(f"GLiNER download failed (will retry on first use): {e}")


def _run_bootstrap():
    """Background bootstrap: install packages then download models."""
    state["start_time"] = time.time()
    try:
        state["phase"] = "packages"
        state["message"] = "Checking dependencies..."
        state["progress_pct"] = 10
        _write_status_file()

        installed = install_missing()
        if installed:
            state["message"] = f"Installed {len(installed)} packages. Loading models..."
        state["progress_pct"] = 40
        _write_status_file()

        state["phase"] = "models"
        state["message"] = "Downloading AI models (~1 GB, first time only)..."
        state["progress_pct"] = 60
        _write_status_file()

        download_models()
        state["progress_pct"] = 90
        state["phase"] = "engine"
        state["message"] = "Initializing PII engine..."
        _write_status_file()

    except Exception as e:
        state["error"] = str(e)
        state["phase"] = "error"
        state["message"] = f"Bootstrap failed: {e}"
        log.error(f"Bootstrap failed: {e}")
    finally:
        if not state["error"]:
            state["phase"] = "ready"
            state["message"] = "PII Shield ready."
            state["progress_pct"] = 100
        state["done"] = True
        _write_status_file()
        log.info("Bootstrap complete.")


def start_background_bootstrap():
    """Launch bootstrap in a daemon thread. Returns immediately."""
    state["start_time"] = time.time()
    t = threading.Thread(target=_run_bootstrap, daemon=True, name="pii-bootstrap")
    t.start()
    return t


def wait_until_ready(timeout: int = 600):
    """Block until bootstrap is done or timeout. Raises on error."""
    deadline = time.time() + timeout
    while not state["done"]:
        if time.time() > deadline:
            raise TimeoutError("Bootstrap timed out after 10 minutes.")
        time.sleep(1)
    if state["error"]:
        raise RuntimeError(f"Bootstrap failed: {state['error']}")
