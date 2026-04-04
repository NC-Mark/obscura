"""
PII Shield — MCP Server (Claude Desktop / Cowork integration)

This is a thin wrapper around the pii_shield package.
All business logic lives in pii_shield/; this file handles only:
  - MCP server setup and tool registration
  - Bootstrap state reporting to Claude
  - Audit logging (proof that no PII leaves the machine via API)

Run (stdio, default):  python mcp_server.py
Run (SSE/HTTP):        python mcp_server.py --sse
"""

import json
import logging
import os
import sys
import threading
import time
from functools import wraps
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [pii-shield] %(message)s",
                    stream=sys.stderr)
log = logging.getLogger("pii-shield.mcp")

# ── Phase 1: install mcp so FastMCP can start (synchronous, ~2s) ─────────────
from pii_shield.bootstrap import install_missing, state as _bstate, _write_status_file
import time as _t
_bstate["start_time"] = _t.time()

try:
    install_missing([("mcp", "mcp[cli]>=1.0.0")])
except Exception as _e:
    log.error(f"MCP install failed: {_e}")

# ── Phase 2+3: heavy packages + models in background ─────────────────────────
from pii_shield.bootstrap import download_models

def _bg_bootstrap():
    try:
        _bstate["phase"] = "packages"
        _bstate["message"] = "Checking dependencies..."
        _write_status_file()
        installed = install_missing()
        if installed:
            _bstate["message"] = f"Installed {len(installed)} packages."
        _bstate["phase"] = "models"
        _bstate["message"] = "Loading AI models..."
        _write_status_file()
        download_models()
        _bstate["phase"] = "engine"
        _bstate["message"] = "Initializing PII engine..."
        _write_status_file()
        # Pre-warm default engine
        from pii_shield import PIIEngine
        domain = os.environ.get("PII_DEFAULT_DOMAIN", "general")
        PIIEngine(domain=domain)._ensure_ready()
        _bstate["phase"] = "ready"
        _bstate["message"] = "PII Shield ready."
    except Exception as e:
        _bstate["error"] = str(e)
        _bstate["phase"] = "error"
        _bstate["message"] = f"Bootstrap failed: {e}"
        log.error(f"Bootstrap failed: {e}")
    finally:
        _bstate["done"] = True
        _write_status_file()

threading.Thread(target=_bg_bootstrap, daemon=True, name="pii-bootstrap").start()

# ── MCP setup ─────────────────────────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("PII Shield", host="127.0.0.1",
              port=int(os.environ.get("PII_PORT", "8765")))

# ── Audit logger ──────────────────────────────────────────────────────────────
_audit_log = logging.getLogger("pii-shield.audit")
_audit_log.propagate = False
_audit_handler = None

def _ensure_audit_log():
    global _audit_handler
    if _audit_handler:
        return
    from pii_shield.config import AUDIT_DIR
    p = AUDIT_DIR / "mcp_audit.log"
    _audit_handler = logging.FileHandler(str(p), mode="a", encoding="utf-8")
    _audit_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _audit_log.addHandler(_audit_handler)

def _audit(func):
    """Decorator: log every MCP tool call and response to audit log."""
    import inspect
    @wraps(func)
    def wrapper(*args, **kwargs):
        _ensure_audit_log()
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        call_args = {params[i]: v for i, v in enumerate(args) if i < len(params)}
        call_args.update(kwargs)
        safe = {k: (v[:200] + "..." if isinstance(v, str) and len(v) > 200 else v)
                for k, v in call_args.items()}
        _audit_log.info(f">>> {func.__name__}({json.dumps(safe, ensure_ascii=False)})")
        try:
            result = func(*args, **kwargs)
            logged = result[:500] + "..." if isinstance(result, str) and len(result) > 500 else result
            _audit_log.info(f"<<< {func.__name__} → {logged}")
            return result
        except Exception as exc:
            _audit_log.info(f"<<< {func.__name__} ERR {exc}")
            raise
    return wrapper


# ── Bootstrap guard ───────────────────────────────────────────────────────────

def _check_ready() -> str | None:
    """Return JSON status string if not ready, else None."""
    if _bstate["done"] and not _bstate.get("error"):
        return None
    if _bstate.get("error"):
        return json.dumps({
            "status": "error",
            "message": f"PII Shield failed: {_bstate['error']}",
            "hint": "Check internet connection, ensure Python 3.10+ is in PATH, restart.",
        })
    elapsed = round(time.time() - (_bstate.get("start_time") or time.time()), 1)
    return json.dumps({
        "status": "loading",
        "phase": _bstate.get("phase", "starting"),
        "message": _bstate.get("message", "Starting up..."),
        "elapsed_seconds": elapsed,
        "hint": "First-time setup takes ~5-10 min. Wait and try again.",
    })


def _get_engine(domain: str = None):
    from pii_shield import PIIEngine
    domain = domain or os.environ.get("PII_DEFAULT_DOMAIN", "general")
    return PIIEngine(domain=domain)


# ── MCP Tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
@_audit
def list_entities() -> str:
    """Show server status, NER backend, supported entity types, and recent sessions."""
    from pii_shield.storage import load_mapping
    from pii_shield.config import MAPPING_DIR

    sessions = sorted(
        (f for f in MAPPING_DIR.glob("*.json") if not f.name.startswith("review_")),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )[:5]
    recent = []
    for s in sessions:
        try:
            d = json.loads(s.read_text())
            recent.append({"session_id": d["session_id"], "entities": len(d["mapping"])})
        except Exception:
            pass

    if not _bstate["done"]:
        return json.dumps({
            "status": "loading",
            "phase": _bstate.get("phase"),
            "message": _bstate.get("message", "Starting..."),
            "recent_sessions": recent,
        }, indent=2)

    if _bstate.get("error"):
        return json.dumps({"status": "error", "message": _bstate["error"],
                           "recent_sessions": recent}, indent=2)

    eng = _get_engine()
    eng._ensure_ready()
    backend = getattr(eng, "_backend", "unknown")
    quality = "full (GLiNER zero-shot)" if "gliner" in backend else "reduced (SpaCy fallback)"
    return json.dumps({
        "status": "ready",
        "backend": backend,
        "quality": quality,
        "domain": eng._domain,
        "recognizers": [type(r).__name__ for r in eng.analyzer.registry.recognizers],
        "recent_sessions": recent,
    }, indent=2, ensure_ascii=False)


@mcp.tool()
@_audit
def anonymize_file(file_path: str, language: str = "en", prefix: str = "",
                   review_session_id: str = "", domain: str = "",
                   profile: str = "") -> str:
    """Anonymize PII in a file. Supports .pdf, .docx, .txt, .md, .csv.
    Returns output_path + session_id. Real content never enters the API.
    Use review_session_id to re-anonymize after HITL review.
    Use profile to apply a named detection profile (overrides domain).
    """
    loading = _check_ready()
    if loading:
        return loading
    from pii_shield.engine.anonymizer import anonymize_file as _anon
    profile_ctx = None
    effective_domain = domain or None
    if profile:
        from pii_shield.profiles import resolve_profile
        profile_ctx = resolve_profile(profile)
        if profile_ctx is None:
            return json.dumps({"error": f"Profile not found: {profile}"})
        effective_domain = profile_ctx.domain
    engine = _get_engine(effective_domain)
    result = _anon(engine, file_path, language, prefix=prefix,
                   review_session_id=review_session_id, profile=profile_ctx)
    if "error" in result:
        return json.dumps(result)
    result["note"] = "Anonymized file at output_path. Read it to get content."
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
@_audit
def anonymize_text(text: str, language: str = "en", prefix: str = "",
                   entity_overrides: str = "", domain: str = "",
                   profile: str = "") -> str:
    """Anonymize PII in plain text. Use anonymize_file for better privacy (file path only in API).
    Use prefix for multi-file workflows. entity_overrides: JSON from HITL review.
    Use profile to apply a named detection profile (overrides domain).
    """
    loading = _check_ready()
    if loading:
        return loading
    from pii_shield.engine.anonymizer import anonymize_text as _anon
    profile_ctx = None
    effective_domain = domain or None
    if profile:
        from pii_shield.profiles import resolve_profile
        profile_ctx = resolve_profile(profile)
        if profile_ctx is None:
            return json.dumps({"error": f"Profile not found: {profile}"})
        effective_domain = profile_ctx.domain
    engine = _get_engine(effective_domain)
    r = _anon(engine, text, language, prefix=prefix, entity_overrides=entity_overrides,
              profile=profile_ctx)
    return json.dumps(r, indent=2, ensure_ascii=False)


@mcp.tool()
@_audit
def deanonymize_text(text: str, session_id: str = "", output_path: str = "") -> str:
    """Restore PII in text. Writes to local file — never returns real values to Claude."""
    from pii_shield.storage import load_mapping, latest_session_id
    from pii_shield.config import MAPPING_DIR
    from pii_shield.engine.deanonymizer import deanonymize_text as _deanon, write_restored_docx

    sid = session_id.strip() or latest_session_id()
    if not sid:
        return json.dumps({"error": "No session. Run anonymize first."})
    mapping = load_mapping(sid)
    if not mapping:
        return json.dumps({"error": f"Mapping not found: {sid}"})

    restored = _deanon(text, mapping)
    out = Path(output_path).expanduser().resolve() if output_path else MAPPING_DIR / f"restored_{sid}.docx"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".docx":
        write_restored_docx(restored, out)
    else:
        out.write_text(restored, encoding="utf-8")

    return json.dumps({
        "restored_path": str(out), "session_id": sid,
        "entities_restored": len(mapping),
        "note": "PII written to file. Not returned to LLM.",
    }, indent=2)


@mcp.tool()
@_audit
def deanonymize_docx(file_path: str, session_id: str = "") -> str:
    """Restore PII in .docx preserving formatting. Returns file path only."""
    from pii_shield.storage import load_mapping, latest_session_id
    from pii_shield.engine.deanonymizer import deanonymize_docx as _deanon

    sid = session_id.strip() or latest_session_id()
    if not sid:
        return json.dumps({"error": "No session. Run anonymize first."})
    mapping = load_mapping(sid)
    if not mapping:
        return json.dumps({"error": f"Mapping not found: {sid}"})
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        return json.dumps({"error": f"Not found: {p}"})
    out = _deanon(p, mapping)
    return json.dumps({"restored_path": out, "session_id": sid}, indent=2)


@mcp.tool()
@_audit
def get_mapping(session_id: str = "") -> str:
    """Return placeholder keys and types only — no real PII values."""
    from pii_shield.storage import load_mapping, latest_session_id

    sid = session_id.strip() or latest_session_id()
    if not sid:
        return json.dumps({"error": "No session."})
    mapping = load_mapping(sid)
    if not mapping:
        return json.dumps({"error": f"Not found: {sid}"})

    safe = {}
    for ph in mapping:
        etype = ph.strip("<>").rsplit("_", 1)[0] if "_" in ph else ph.strip("<>")
        safe[ph] = etype
    return json.dumps({
        "session_id": sid, "total_entities": len(mapping),
        "placeholders": safe,
        "note": "Real values not returned. Use deanonymize_* to restore to file.",
    }, indent=2)


@mcp.tool()
@_audit
def scan_text(text: str, language: str = "en", domain: str = "") -> str:
    """Detect PII without anonymizing. Preview mode — returns types and positions, not real text."""
    loading = _check_ready()
    if loading:
        return loading
    engine = _get_engine(domain or None)
    entities = engine.detect(text, language)
    safe = [{"type": e["type"], "start": e["start"], "end": e["end"],
             "score": e["score"], "verified": e.get("verified"),
             "reason": e.get("reason", "")} for e in entities]
    return json.dumps({
        "entities_found": len(entities),
        "confirmed": sum(1 for e in entities if e.get("verified")),
        "entities": safe,
    }, indent=2)


@mcp.tool()
@_audit
def find_file(filename: str) -> str:
    """Find a file by name in the configured working directory."""
    work_dir = os.environ.get("PII_WORK_DIR", "").strip()
    if not work_dir:
        return json.dumps({"error": "Working directory not set.",
                           "hint": "Set PII_WORK_DIR env var or configure in Settings > Extensions."})
    wd = Path(work_dir).expanduser().resolve()
    if not wd.exists():
        return json.dumps({"error": f"work_dir does not exist: {work_dir}"})
    matches = []
    try:
        for f in wd.rglob(filename):
            if f.is_file():
                matches.append(str(f))
                if len(matches) >= 10:
                    break
    except PermissionError:
        pass
    if matches:
        return json.dumps({"matches": matches, "count": len(matches)})
    return json.dumps({"error": f"'{filename}' not found in {work_dir}"})


@mcp.tool()
@_audit
def start_review(session_id: str = "") -> str:
    """Start local HITL review server. Returns URL for user to open in browser."""
    from pii_shield.storage import get_review as _get_review, latest_session_id
    from pii_shield.review import get_review_url

    sid = session_id.strip() or latest_session_id()
    if not sid:
        return json.dumps({"error": "No session. Run anonymize_file first."})
    review = _get_review(sid)
    if not review:
        return json.dumps({"error": f"No review data for {sid}. Run anonymize_file first."})

    url = get_review_url(sid)
    if url is None:
        return json.dumps({"error": "Could not start review server."})

    return json.dumps({
        "url": url, "session_id": sid,
        "entities_count": len(review.get("confirmed", [])),
        "note": "Present URL to user via AskUserQuestion. Do NOT open browser automatically.",
    }, indent=2)


@mcp.tool()
@_audit
def get_review_status(session_id: str = "") -> str:
    """Check if HITL review was approved. Returns status + has_changes only (no PII)."""
    from pii_shield.storage import get_review as _get_review, latest_session_id

    sid = session_id.strip() or latest_session_id()
    if not sid:
        return json.dumps({"error": "No session."})
    review = _get_review(sid)
    if not review:
        return json.dumps({"error": f"No review for {sid}"})

    overrides = review.get("overrides", {"remove": [], "add": []})
    has_changes = bool(overrides.get("remove") or overrides.get("add"))
    return json.dumps({
        "status": review.get("status", "pending"),
        "has_changes": has_changes,
        "session_id": sid,
    }, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PII Shield MCP Server")
    parser.add_argument("--sse", action="store_true", help="Run as SSE/HTTP server")
    args = parser.parse_args()

    if args.sse:
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
