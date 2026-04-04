"""
PII Shield — Interactive Setup Script

Run:
    py setup.py                      # guided interactive setup
    py setup.py --model small        # skip model prompt, use small
    py setup.py --model large --domain financial
    py setup.py --check              # verify existing install only

What it does:
  1. Installs all pip dependencies (requirements.txt)
  2. Downloads the spaCy English model
  3. Asks which GLiNER model to use (or uses --model flag)
  4. Downloads the chosen GLiNER model
  5. Saves the choice to ~/.pii_shield/config.json
  6. Writes a quick smoke-test to confirm detection works
"""

import argparse
import json
import subprocess
import sys
import textwrap
from pathlib import Path

# ── Helpers ───────────────────────────────────────────────────────────────────

def _print(msg: str = "", indent: int = 0):
    prefix = "  " * indent
    for line in msg.splitlines():
        print(prefix + line)

def _ok(msg: str):
    print(f"  [OK]  {msg}")

def _warn(msg: str):
    print(f"  [!!]  {msg}")

def _err(msg: str):
    print(f"  [ERR] {msg}")

def _run(cmd: list[str], desc: str, capture: bool = False) -> subprocess.CompletedProcess:
    print(f"\n  >> {desc}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        _err(f"Command failed (exit {result.returncode})")
        if capture and result.stderr:
            print(textwrap.indent(result.stderr[-2000:], "     "))
        sys.exit(1)
    return result


# ── GLiNER model table ────────────────────────────────────────────────────────

GLINER_MODELS = {
    "small": {
        "id":   "urchade/gliner_small-v2.1",
        "size": "~170 MB",
        "desc": "Fast, good quality — recommended default",
    },
    "medium": {
        "id":   "urchade/gliner_medium-v2.1",
        "size": "~340 MB",
        "desc": "Better accuracy on ambiguous names, moderate speed",
    },
    "large": {
        "id":   "urchade/gliner_large-v2.1",
        "size": "~680 MB",
        "desc": "Best accuracy, slower — use when quality is critical",
    },
    "multilingual": {
        "id":   "urchade/gliner_multi-v2.1",
        "size": "~340 MB",
        "desc": "Multi-language support (English + EU languages)",
    },
}

VALID_MODEL_KEYS = list(GLINER_MODELS.keys())

VALID_DOMAINS = ["general", "legal", "financial", "healthcare"]


# ── Step functions ────────────────────────────────────────────────────────────

def step_install_deps():
    """Install packages from requirements.txt."""
    req = Path(__file__).parent / "requirements.txt"
    if not req.exists():
        _err(f"requirements.txt not found at {req}")
        sys.exit(1)
    print("  (This may take several minutes on first run — you will see pip output below)")
    print()
    _run(
        [sys.executable, "-m", "pip", "install", "-r", str(req)],
        "Installing pip dependencies from requirements.txt",
        capture=False,
    )
    _ok("pip dependencies installed")


_TORCH_PROBE = (
    "import torch; t=torch.zeros(1); "
    "print(torch.__version__ + ' CPU' if not torch.cuda.is_available() else torch.__version__ + ' CUDA')"
)


def _torch_ok() -> tuple[bool, str]:
    """Test torch in a fresh subprocess. Returns (ok, message)."""
    result = subprocess.run(
        [sys.executable, "-c", _TORCH_PROBE],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return True, result.stdout.strip()
    return False, (result.stderr or result.stdout).strip()[-300:]


def step_install_torch():
    """Install PyTorch 2.2.2 CPU-only and pinned onnxruntime — both known to work on Windows."""
    print("\n  (Downloading ~200 MB — this will take a minute or two)")
    print()
    _run(
        [
            sys.executable, "-m", "pip", "install",
            "torch==2.4.1+cpu",
            "--index-url", "https://download.pytorch.org/whl/cpu",
            "--no-cache-dir",
        ],
        "Installing PyTorch 2.4.1 (CPU-only)",
        capture=False,
    )
    _ok("PyTorch 2.4.1 (CPU) installed")

    # onnxruntime 1.24+ has DLL init issues on Windows — pin to a stable version
    print()
    _run(
        [
            sys.executable, "-m", "pip", "install",
            "onnxruntime==1.17.3",
            "--no-cache-dir", "--quiet",
        ],
        "Installing onnxruntime 1.17.3 (stable Windows build)",
        capture=False,
    )
    _ok("onnxruntime 1.17.3 installed")


def _check_vcruntime():
    """Warn if the Visual C++ runtime DLLs are missing (required by PyTorch)."""
    import ctypes
    missing = []
    for dll in ("VCRUNTIME140.dll", "MSVCP140.dll", "VCRUNTIME140_1.dll"):
        try:
            ctypes.WinDLL(dll)
        except OSError:
            missing.append(dll)
    if missing:
        print()
        _warn(f"Missing Visual C++ runtime DLLs: {', '.join(missing)}")
        print()
        print("  PyTorch requires the Microsoft Visual C++ Redistributable.")
        print("  Download and install it (it's free, ~25 MB), then run install.bat again:")
        print()
        print("  https://aka.ms/vs/17/release/vc_redist.x64.exe")
        print()
        sys.exit(1)
    else:
        _ok("Visual C++ runtime present")


def step_check_torch():
    """
    Verify PyTorch loads correctly.

    On Windows the most common failure is a DLL error caused by a CUDA build of
    torch being installed when the matching CUDA drivers are absent (common with
    Anaconda environments).  We detect this and offer to reinstall the CPU-only
    build, which works on every machine and is sufficient for PII detection.

    Verification always runs in a subprocess because a DLL that fails to load
    in the current process cannot be retried in the same process.
    """
    print("\n  >> Checking PyTorch...")
    ok, msg = _torch_ok()
    if ok:
        _ok(f"PyTorch {msg}")
        return

    _warn(f"PyTorch failed to load: {msg.splitlines()[-1] if msg else 'unknown error'}")
    print()
    print("  This usually means the installed PyTorch build requires CUDA drivers")
    print("  that are not present on this machine (common with Anaconda).")
    print()
    print("  The fix is to reinstall PyTorch (CPU-only).  This works on all")
    print("  machines and is sufficient for PII detection — no GPU needed.")
    print()
    # Check for Visual C++ runtime before attempting reinstall
    _check_vcruntime()

    raw = input("  Reinstall PyTorch (CPU-only) now? [Y/n]: ").strip().lower()
    if raw not in ("", "y", "yes"):
        _warn("Skipping PyTorch fix — setup may fail at model download step.")
        return

    _run(
        [
            sys.executable, "-m", "pip", "install",
            "torch==2.4.1+cpu",
            "--index-url", "https://download.pytorch.org/whl/cpu",
            "--force-reinstall", "--no-cache-dir",
        ],
        "Reinstalling PyTorch 2.2.2 (CPU-only, no cache)",
        capture=False,
    )

    # Verify in a fresh subprocess — can't reload DLLs in the current process
    print("  >> Verifying PyTorch in fresh process...")
    ok2, msg2 = _torch_ok()
    if ok2:
        _ok(f"PyTorch {msg2} (CPU) — ready")
    else:
        _err(f"PyTorch still failing: {msg2.splitlines()[-1] if msg2 else 'unknown'}")
        print()
        print("  Manual fix — run these two commands in a new terminal, then")
        print("  run install.bat again:")
        print()
        print(f'    "{sys.executable}" -m pip install torch --index-url https://download.pytorch.org/whl/cpu --force-reinstall --no-cache-dir')
        print()
        sys.exit(1)


def step_spacy_model():
    """Download the spaCy English model if not already present."""
    print("\n  >> Checking spaCy English model...")
    try:
        import spacy  # noqa: F401
        try:
            import en_core_web_sm  # noqa: F401
            _ok("spaCy model en_core_web_sm already present")
            return
        except ImportError:
            pass
    except ImportError:
        _warn("spaCy not yet importable — will install anyway")

    _run(
        [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
        "Downloading spaCy English model",
        capture=False,
    )
    _ok("spaCy en_core_web_sm downloaded")


DOMAIN_DESCRIPTIONS = {
    "general":    "All domains combined — good starting point",
    "financial":  "Financial markets: client names, LEI, ISIN, SWIFT, account numbers",
    "legal":      "Legal documents: party names, case refs, contract terms",
    "healthcare": "Healthcare: patient names, NPI, DEA, MRN, Medicare IDs",
}


def step_choose_domain(preset: str | None) -> str:
    """Return the default domain, prompting if not preset."""
    if preset and preset != "general":
        if preset not in VALID_DOMAINS:
            _err(f"Unknown domain '{preset}'. Valid: {', '.join(VALID_DOMAINS)}")
            sys.exit(1)
        _ok(f"Using domain: {preset}")
        return preset

    print()
    print("  ┌─────────────────────────────────────────────────────────────────┐")
    print("  │               Choose your default detection domain              │")
    print("  │  This sets which stoplist and recognizers are active by default.│")
    print("  └─────────────────────────────────────────────────────────────────┘")
    print()

    for i, domain in enumerate(VALID_DOMAINS, start=1):
        marker = " (default)" if domain == "general" else ""
        print(f"  [{i}] {domain:<12}  {DOMAIN_DESCRIPTIONS[domain]}{marker}")

    print()
    while True:
        raw = input("  Enter number or name [1]: ").strip()
        if raw == "" or raw == "1":
            return "general"
        if raw in VALID_DOMAINS:
            return raw
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(VALID_DOMAINS):
                return VALID_DOMAINS[idx]
        except ValueError:
            pass
        _warn(f"Invalid choice '{raw}'. Enter 1-{len(VALID_DOMAINS)} or a name.")


def step_choose_model(preset: str | None) -> str:
    """Return the GLiNER model key, prompting if not preset."""
    if preset:
        if preset not in GLINER_MODELS:
            _err(f"Unknown model '{preset}'. Valid: {', '.join(VALID_MODEL_KEYS)}")
            sys.exit(1)
        _ok(f"Using GLiNER model: {preset} ({GLINER_MODELS[preset]['id']})")
        return preset

    # Interactive prompt
    print()
    print("  ┌─────────────────────────────────────────────────────────────────┐")
    print("  │              Choose your GLiNER detection model                 │")
    print("  │  Larger models are more accurate but use more RAM / download.   │")
    print("  └─────────────────────────────────────────────────────────────────┘")
    print()

    for i, (key, info) in enumerate(GLINER_MODELS.items(), start=1):
        marker = " (default)" if key == "small" else ""
        print(f"  [{i}] {key:<14}  {info['size']:<10}  {info['desc']}{marker}")

    print()
    while True:
        raw = input("  Enter number or name [1]: ").strip()
        if raw == "" or raw == "1":
            return "small"
        if raw in GLINER_MODELS:
            return raw
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(GLINER_MODELS):
                return VALID_MODEL_KEYS[idx]
        except ValueError:
            pass
        _warn(f"Invalid choice '{raw}'. Enter 1-{len(GLINER_MODELS)} or a name.")


def step_download_gliner(model_key: str):
    """Download the chosen GLiNER model via the gliner library."""
    model_id = GLINER_MODELS[model_key]["id"]
    print(f"\n  >> Downloading GLiNER model: {model_id}")
    print(f"     Size: {GLINER_MODELS[model_key]['size']} — this may take a few minutes on first run.")

    try:
        from gliner import GLiNER
        GLiNER.from_pretrained(model_id)
        _ok(f"GLiNER model '{model_key}' ready")
    except Exception as e:
        _err(f"Model download failed: {e}")
        _warn("Check your internet connection and try again.")
        sys.exit(1)


def step_save_config(model_key: str, domain: str):
    """Save chosen model and domain to ~/.pii_shield/config.json."""
    pii_dir = Path.home() / ".pii_shield"
    pii_dir.mkdir(parents=True, exist_ok=True)
    config_file = pii_dir / "config.json"

    cfg: dict = {}
    if config_file.exists():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    cfg["gliner_model"] = GLINER_MODELS[model_key]["id"]
    cfg["gliner_model_key"] = model_key
    cfg["default_domain"] = domain

    config_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    _ok(f"Saved config → {config_file}")


def step_smoke_test():
    """Quick end-to-end smoke test to confirm everything works."""
    print("\n  >> Running smoke test...")
    try:
        # Add server dir to path so pii_shield is importable
        server_dir = str(Path(__file__).parent)
        if server_dir not in sys.path:
            sys.path.insert(0, server_dir)

        from pii_shield import PIIEngine
        engine = PIIEngine(domain="general")
        engine._ensure_ready()

        sample = "Please contact John Smith at john.smith@example.com or call 555-123-4567."
        entities = engine.detect(sample, "en")
        confirmed = [e for e in entities if e.get("verified")]

        if not confirmed:
            _warn("Smoke test: no entities detected — engine loaded but may need a moment.")
        else:
            types_found = sorted({e["type"] for e in confirmed})
            _ok(f"Smoke test passed — detected: {', '.join(types_found)}")
    except Exception as e:
        _warn(f"Smoke test failed: {e}")
        _warn("Installation may still work — run the server and check /status")


def step_check_only():
    """Just verify what's installed without changing anything."""
    print("\n  Checking existing installation...\n")

    # Python version
    v = sys.version_info
    if v >= (3, 10):
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _warn(f"Python {v.major}.{v.minor}.{v.micro} — 3.10+ recommended")

    # Key packages
    checks = [
        ("gliner",             "GLiNER"),
        ("presidio_analyzer",  "Presidio Analyzer"),
        ("spacy",              "spaCy"),
        ("fastapi",            "FastAPI"),
        ("uvicorn",            "Uvicorn"),
        ("pdfplumber",         "pdfplumber"),
        ("docx",               "python-docx"),
        ("stdnum",             "python-stdnum"),
    ]
    for module, label in checks:
        try:
            __import__(module)
            _ok(label)
        except ImportError:
            _warn(f"{label} — NOT installed")

    # spaCy model
    try:
        import en_core_web_sm  # noqa: F401
        _ok("spaCy en_core_web_sm")
    except ImportError:
        _warn("spaCy en_core_web_sm — NOT downloaded (run: py -m spacy download en_core_web_sm)")

    # Config file
    cfg_path = Path.home() / ".pii_shield" / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
            model_id  = cfg.get("gliner_model", "not set")
            domain    = cfg.get("default_domain", "general")
            _ok(f"Config: model={model_id}, domain={domain}")
        except Exception:
            _warn("Config file exists but could not be parsed")
    else:
        _warn("No config file — run setup.py to configure")

    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PII Shield setup — installs dependencies and configures the GLiNER model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          py setup.py                         # interactive setup
          py setup.py --model small           # skip model prompt
          py setup.py --model large --domain financial
          py setup.py --check                 # verify existing install
        """),
    )
    parser.add_argument("--model",
                        choices=VALID_MODEL_KEYS + [""],
                        default="",
                        metavar="{" + "|".join(VALID_MODEL_KEYS) + "}",
                        help="GLiNER model size to download and use")
    parser.add_argument("--domain",
                        choices=VALID_DOMAINS,
                        default="general",
                        help="Default detection domain (default: general)")
    parser.add_argument("--check",
                        action="store_true",
                        help="Verify existing install without making changes")
    parser.add_argument("--skip-deps",
                        action="store_true",
                        help="Skip pip install step (useful if deps already installed)")
    parser.add_argument("--skip-download",
                        action="store_true",
                        help="Skip model download (use after model is already cached)")
    args = parser.parse_args()

    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║          PII Shield — Setup              ║")
    print("  ╚══════════════════════════════════════════╝")
    print()

    if args.check:
        step_check_only()
        return

    # ── 1. Install deps (torch excluded — handled next) ───────────────────────
    if not args.skip_deps:
        step_install_deps()
        step_install_torch()
    else:
        _ok("Skipping pip install (--skip-deps)")

    # ── 2. Verify PyTorch loaded correctly ────────────────────────────────────
    step_check_torch()

    # ── 3. spaCy model ────────────────────────────────────────────────────────
    step_spacy_model()

    # ── 4. Choose default domain ──────────────────────────────────────────────
    domain = step_choose_domain(args.domain if args.domain != "general" else None)

    # ── 5. Choose GLiNER model ────────────────────────────────────────────────
    model_key = step_choose_model(args.model or None)

    # ── 6. Download GLiNER model ──────────────────────────────────────────────
    if not args.skip_download:
        step_download_gliner(model_key)
    else:
        _ok(f"Skipping model download (--skip-download) — using {model_key}")

    # ── 7. Save config ────────────────────────────────────────────────────────
    step_save_config(model_key, domain)

    # ── 8. Smoke test ─────────────────────────────────────────────────────────
    step_smoke_test()

    # ── Done ──────────────────────────────────────────────────────────────────
    print()
    print("  ─────────────────────────────────────────────────────────────")
    print("  Setup complete.")
    print()
    print("  Start the REST API server:")
    print("    py api_server.py")
    print()
    print("  Or run the MCP server (Claude Desktop):")
    print("    py mcp_server.py")
    print()
    print("  API docs (once server is running):")
    print("    http://localhost:8080/docs")
    print("  ─────────────────────────────────────────────────────────────")
    print()


if __name__ == "__main__":
    main()
