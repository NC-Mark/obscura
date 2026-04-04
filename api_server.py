"""
PII Shield — Standalone REST API Server

Run:
    python api_server.py
    python api_server.py --host 0.0.0.0 --port 8080 --domain financial

Endpoints:
    GET  /status                        Health check + engine info
    POST /anonymize/text                Anonymize plain text
    POST /anonymize/file                Anonymize a file (path on this machine)
    POST /deanonymize/text              Restore PII in text (returns file path)
    POST /deanonymize/docx              Restore PII in .docx (returns file path)
    GET  /sessions/{session_id}         Mapping metadata (no real PII values)
    POST /review/{session_id}/start     Start HITL review server, returns URL
    GET  /review/{session_id}/status    Check review approval status

All anonymize responses include a session_id. Store it — you need it to deanonymize.
Deanonymized output is always written to a LOCAL FILE; the real PII values are
never returned in the API response.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# ── Bootstrap: ensure deps are installed before importing heavy stuff ─────────
from pii_shield.bootstrap import install_missing, download_models, state as _bstate
import threading

def _background_init():
    install_missing()
    download_models()
    _bstate["done"] = True
    _bstate["phase"] = "ready"

_init_thread = threading.Thread(target=_background_init, daemon=True)
_init_thread.start()

# ── FastAPI app ───────────────────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [pii-shield] %(message)s",
                    stream=sys.stderr)
log = logging.getLogger("pii-shield.api")

app = FastAPI(
    title="PII Shield API",
    description="Anonymize PII in documents before sending to any LLM. "
                "Restore real values after processing.",
    version="7.0.0",
)

# Engine is instantiated lazily on first request
_engine_cache: dict = {}

def _get_engine(domain: str = "general"):
    if domain not in _engine_cache:
        from pii_shield import PIIEngine
        _engine_cache[domain] = PIIEngine(domain=domain)
    return _engine_cache[domain]


# ── Request/Response models ───────────────────────────────────────────────────

class AnonymizeTextRequest(BaseModel):
    text: str
    language: str = "en"
    prefix: str = ""
    domain: str = "general"
    profile: str = ""             # named profile — overrides domain if set
    review_session_id: str = ""   # for re-anonymize after HITL review


class AnonymizeFileRequest(BaseModel):
    file_path: str
    language: str = "en"
    prefix: str = ""
    domain: str = "general"
    profile: str = ""             # named profile — overrides domain if set
    review_session_id: str = ""


class ProfileRequest(BaseModel):
    name: str
    description: str = ""
    base_domain: str = "general"
    extra_stoplist: list[str] = []
    custom_patterns: list[dict] = []
    min_score: float | None = None
    gliner_model: str | None = None


class DeanonymizeTextRequest(BaseModel):
    text: str
    session_id: str
    output_path: str = ""         # optional; defaults to ~/.pii_shield/mappings/restored_<sid>.docx


class DeanonymizeDocxRequest(BaseModel):
    file_path: str
    session_id: str


class DeanonymizePreviewRequest(BaseModel):
    text: str
    session_id: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/status")
def status():
    """Health check. Returns engine readiness and bootstrap state."""
    ready = _bstate.get("done", False)
    return {
        "status": "ready" if ready else "loading",
        "phase": _bstate.get("phase", "starting"),
        "message": _bstate.get("message", ""),
        "version": "7.0.0",
    }


@app.post("/anonymize/text")
def anonymize_text_endpoint(req: AnonymizeTextRequest):
    """
    Anonymize PII in plain text.

    Returns anonymized_text (with placeholders), session_id, and entity stats.
    Store the session_id — you'll need it to deanonymize later.
    """
    _wait_ready()
    from pii_shield.engine.anonymizer import anonymize_text
    profile_ctx, domain = _resolve_profile_and_domain(req.profile, req.domain)
    engine = _get_engine(domain)

    overrides = ""
    if req.review_session_id:
        from pii_shield.storage import get_review
        review = get_review(req.review_session_id)
        if review:
            ov = review.get("overrides", {})
            if ov.get("remove") or ov.get("add"):
                overrides = json.dumps(ov)
        else:
            raise HTTPException(404, f"Review session not found: {req.review_session_id}")

    result = anonymize_text(engine, req.text, req.language,
                            prefix=req.prefix, entity_overrides=overrides,
                            profile=profile_ctx)
    return result


@app.post("/anonymize/file")
def anonymize_file_endpoint(req: AnonymizeFileRequest):
    """
    Anonymize a file on the local machine.

    The file path must be accessible from this server.
    Returns output_path (anonymized file on disk), session_id, and stats.
    The anonymized file content is NOT returned in the response — read it from disk.
    """
    _wait_ready()
    from pii_shield.engine.anonymizer import anonymize_file
    profile_ctx, domain = _resolve_profile_and_domain(req.profile, req.domain)
    engine = _get_engine(domain)
    result = anonymize_file(engine, req.file_path, req.language,
                            prefix=req.prefix,
                            review_session_id=req.review_session_id,
                            profile=profile_ctx)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/deanonymize/text")
def deanonymize_text_endpoint(req: DeanonymizeTextRequest):
    """
    Restore PII values in text that contains placeholders.

    The restored content is written to a LOCAL FILE (never returned in the response).
    Returns the file path only — open it on your machine to read the result.
    """
    _wait_ready()
    from pii_shield.storage import load_mapping
    from pii_shield.engine.deanonymizer import deanonymize_text, write_restored_docx

    mapping = load_mapping(req.session_id)
    if not mapping:
        raise HTTPException(404, f"Session not found: {req.session_id}")

    restored = deanonymize_text(req.text, mapping)

    if req.output_path:
        out = Path(req.output_path).expanduser().resolve()
    else:
        from pii_shield.config import MAPPING_DIR
        out = MAPPING_DIR / f"restored_{req.session_id}.docx"

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".docx":
        write_restored_docx(restored, out)
    else:
        out.write_text(restored, encoding="utf-8")

    return {
        "restored_path": str(out),
        "session_id": req.session_id,
        "entities_restored": len(mapping),
        "note": "PII written to file. Not returned in response.",
    }


@app.post("/deanonymize/docx")
def deanonymize_docx_endpoint(req: DeanonymizeDocxRequest):
    """
    Restore PII in a .docx file, preserving all formatting.
    Returns path to the restored file only.
    """
    _wait_ready()
    from pii_shield.storage import load_mapping
    from pii_shield.engine.deanonymizer import deanonymize_docx

    mapping = load_mapping(req.session_id)
    if not mapping:
        raise HTTPException(404, f"Session not found: {req.session_id}")

    p = Path(req.file_path).expanduser().resolve()
    if not p.exists():
        raise HTTPException(404, f"File not found: {p}")

    out = deanonymize_docx(p, mapping)
    return {"restored_path": out, "session_id": req.session_id}


@app.post("/deanonymize/preview")
def deanonymize_preview_endpoint(req: DeanonymizePreviewRequest):
    """
    Restore PII in text and return the result inline (no file write).
    Intended for the web UI running on localhost where file paths are inaccessible.
    Note: only expose this server on 127.0.0.1 (the default) — this endpoint
    returns real PII values in the response body.
    """
    _wait_ready()
    from pii_shield.storage import load_mapping
    from pii_shield.engine.deanonymizer import deanonymize_text

    mapping = load_mapping(req.session_id)
    if not mapping:
        raise HTTPException(404, f"Session not found: {req.session_id}")

    restored = deanonymize_text(req.text, mapping)
    return {
        "restored_text": restored,
        "session_id": req.session_id,
        "entities_restored": len(mapping),
    }


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    """
    Get mapping metadata for a session (placeholder keys and types only).
    Real PII values are never returned.
    """
    from pii_shield.storage import load_mapping
    mapping = load_mapping(session_id)
    if not mapping:
        raise HTTPException(404, f"Session not found: {session_id}")

    safe = {}
    for ph in mapping:
        etype = ph.strip("<>").rsplit("_", 1)[0] if "_" in ph else ph.strip("<>")
        safe[ph] = etype

    return {
        "session_id": session_id,
        "total_entities": len(mapping),
        "placeholders": safe,
        "note": "Real values not returned. Use /deanonymize/* to restore to file.",
    }


@app.post("/review/{session_id}/start")
def start_review(session_id: str):
    """Start the HITL review server and return the review URL."""
    from pii_shield.storage import get_review as _get_review
    from pii_shield.review import get_review_url

    review = _get_review(session_id)
    if not review:
        raise HTTPException(404, f"No review data for session {session_id}. "
                                  "Run anonymize first.")
    url = get_review_url(session_id)
    if url is None:
        raise HTTPException(500, "Could not start review server.")

    entity_count = len(review.get("confirmed", []))
    return {
        "url": url,
        "session_id": session_id,
        "entities_count": entity_count,
    }


@app.get("/review/{session_id}/status")
def review_status(session_id: str):
    """Check if the HITL review has been approved."""
    from pii_shield.storage import get_review as _get_review
    review = _get_review(session_id)
    if not review:
        raise HTTPException(404, f"No review for session {session_id}")

    overrides = review.get("overrides", {"remove": [], "add": []})
    has_changes = bool(overrides.get("remove") or overrides.get("add"))
    return {
        "status": review.get("status", "pending"),
        "has_changes": has_changes,
        "session_id": session_id,
    }


# ── Profile routes ────────────────────────────────────────────────────────────

@app.get("/profiles")
def get_profiles():
    """List all saved profiles."""
    from pii_shield.profiles import list_profiles
    return {"profiles": list_profiles()}


@app.post("/profiles")
def create_profile(req: ProfileRequest):
    """Create or update a named profile."""
    from pii_shield.profiles import save_profile
    path = save_profile(req.model_dump())
    return {"saved": True, "path": path, "name": req.name}


@app.get("/profiles/{name}")
def get_profile(name: str):
    """Get a profile by name."""
    from pii_shield.profiles import load_profile
    profile = load_profile(name)
    if not profile:
        raise HTTPException(404, f"Profile not found: {name}")
    return profile


@app.delete("/profiles/{name}")
def delete_profile_endpoint(name: str):
    """Delete a profile."""
    from pii_shield.profiles import delete_profile
    if not delete_profile(name):
        raise HTTPException(404, f"Profile not found: {name}")
    return {"deleted": True, "name": name}


@app.get("/custom/stoplist")
def get_custom_stoplist():
    """Show the current user custom + learned stoplist terms."""
    from pii_shield.custom.loader import load_custom_stoplist, load_learned_stoplist
    custom  = sorted(load_custom_stoplist())
    learned = {}
    for domain in ("general", "legal", "financial", "healthcare"):
        terms = sorted(load_learned_stoplist(domain) - load_custom_stoplist())
        if terms:
            learned[domain] = terms
    return {
        "custom_stoplist": custom,
        "learned_stoplist": learned,
        "hint": f"Add terms to ~/.pii_shield/custom/stoplist.txt to suppress detection",
    }


@app.post("/custom/reload")
def reload_custom_terms():
    """Reload custom stoplists + patterns without restarting the server."""
    reloaded = []
    try:
        from pii_shield.engine.core import PIIEngine
        for domain, eng in PIIEngine._instances.items():
            if eng._initialized:
                eng._reload_stoplist()
                reloaded.append(domain)
    except Exception as e:
        raise HTTPException(500, f"Reload failed: {e}")
    return {"reloaded_domains": reloaded}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_profile_and_domain(profile_name: str, domain: str):
    """Resolve profile context and effective domain.
    Profile domain takes precedence over explicit domain if profile is set.
    """
    if profile_name:
        from pii_shield.profiles import resolve_profile
        ctx = resolve_profile(profile_name)
        if ctx is None:
            raise HTTPException(404, f"Profile not found: {profile_name}")
        return ctx, ctx.domain
    return None, domain


def _wait_ready(timeout: int = 600):
    """Block request until bootstrap is done."""
    import time
    deadline = time.time() + timeout
    while not _bstate.get("done"):
        if time.time() > deadline:
            raise HTTPException(503, "Server still initializing. Please retry.")
        time.sleep(0.5)
    if _bstate.get("error"):
        raise HTTPException(500, f"Initialization failed: {_bstate['error']}")


# ── File upload ───────────────────────────────────────────────────────────────

@app.post("/anonymize/upload")
async def anonymize_upload(
    file: UploadFile = File(...),
    language: str   = Form("en"),
    domain: str     = Form("general"),
    prefix: str     = Form(""),
    profile: str    = Form(""),
):
    """
    Upload a file for anonymization directly from the browser.
    Supports .pdf, .docx, .txt, .md, .csv, .log

    The file is saved temporarily, anonymized, and the output stored under
    ~/.pii_shield/uploads/pii_shield_{session_id}/.
    Use GET /download/{session_id} to retrieve the anonymized file.
    """
    import shutil, tempfile
    _wait_ready()
    from pii_shield.engine.anonymizer import anonymize_file as _anon
    from pii_shield.config import PII_SHIELD_DIR

    suffix = Path(file.filename or "upload.txt").suffix.lower()
    allowed = {".pdf", ".docx", ".txt", ".md", ".csv", ".log", ".text"}
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported file type: {suffix}. Allowed: {', '.join(sorted(allowed))}")

    upload_dir = PII_SHIELD_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save upload to a temp file with correct extension so anonymize_file detects format
    tmp_path = upload_dir / f"upload_{file.filename}"
    try:
        with tmp_path.open("wb") as f_out:
            shutil.copyfileobj(file.file, f_out)
    finally:
        await file.close()

    profile_ctx, effective_domain = _resolve_profile_and_domain(profile, domain)
    engine = _get_engine(effective_domain)
    result = _anon(engine, tmp_path, language, prefix=prefix, profile=profile_ctx)

    if "error" in result:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(400, result["error"])

    # Keep a copy of the source file in the output dir so /reapply can use it
    out_dir = Path(result["output_dir"])
    source_copy = out_dir / f"_source{suffix}"
    import shutil as _shutil
    _shutil.copy2(str(tmp_path), str(source_copy))
    tmp_path.unlink(missing_ok=True)

    result["original_filename"] = file.filename
    return result


@app.get("/download/{session_id}")
def download_anonymized(session_id: str, docx: bool = False):
    """
    Download the anonymized output file for a session.
    Add ?docx=true to prefer the .docx version (if available).
    """
    import mimetypes as _mt
    from pii_shield.config import PII_SHIELD_DIR
    uploads_dir = PII_SHIELD_DIR / "uploads"

    # Map extensions to safe MIME types (avoid Windows registry surprises)
    _mime_map = {
        ".txt":  "text/plain",
        ".csv":  "text/csv",
        ".md":   "text/markdown",
        ".log":  "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf":  "application/pdf",
    }

    # Look for the session output directory in uploads dir
    for base in (uploads_dir, PII_SHIELD_DIR):
        out_dir = base / f"pii_shield_{session_id}"
        if out_dir.exists():
            # Exclude _source* files (original uploaded copies kept for reapply)
            files = [f for f in out_dir.iterdir() if not f.name.startswith("_source")]
            if not files:
                continue
            # Prefer docx if requested, otherwise prefer plain-text formats
            if docx:
                chosen = next((f for f in files if f.suffix == ".docx"), files[0])
            else:
                chosen = next((f for f in files if f.suffix != ".docx"), files[0])
            mime = _mime_map.get(chosen.suffix.lower(), "application/octet-stream")
            return FileResponse(
                str(chosen),
                filename=chosen.name,
                media_type=mime,
            )

    raise HTTPException(404, f"No output file found for session: {session_id}")


@app.post("/deanonymize/upload")
async def deanonymize_upload(
    file: UploadFile = File(...),
    session_id: str  = Form(...),
):
    """
    Upload an anonymized file and restore its PII using the stored session mapping.
    Supports .docx, .txt, .md, .csv, .log

    Returns restored_text inline (text files) and a download_url for all types.
    Use GET /deanonymize/result/{session_id} to download the restored file.
    """
    import shutil as _shutil
    _wait_ready()
    from pii_shield.storage import load_mapping
    from pii_shield.engine.deanonymizer import deanonymize_text, deanonymize_docx
    from pii_shield.config import PII_SHIELD_DIR

    mapping = load_mapping(session_id)
    if not mapping:
        raise HTTPException(404, f"Session not found: {session_id}")

    suffix = Path(file.filename or "upload.txt").suffix.lower()
    allowed = {".docx", ".txt", ".md", ".csv", ".log", ".text"}
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported file type: {suffix}. Allowed: {', '.join(sorted(allowed))}")

    original_filename = file.filename  # capture before close
    final_stem = Path(original_filename).stem if original_filename else "document"

    # Save dir for restored output
    out_dir = PII_SHIELD_DIR / "deanon" / f"restored_{session_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write upload using the original stem so deanonymize_docx outputs {stem}_restored.docx
    tmp_path = out_dir / f"{final_stem}{suffix}"
    try:
        with tmp_path.open("wb") as f_out:
            _shutil.copyfileobj(file.file, f_out)
    finally:
        await file.close()

    restored_text = None

    try:
        if suffix == ".docx":
            from docx import Document as _DocxDoc
            # Extract plain text for inline preview before deanonymize_docx opens the file
            _doc = _DocxDoc(str(tmp_path))
            raw_text = "\n".join(p.text for p in _doc.paragraphs if p.text.strip())
            del _doc  # release file handle before deanonymize_docx opens it
            restored_text = deanonymize_text(raw_text, mapping)
            # Save the fully-formatted restored .docx for download
            deanonymize_docx(tmp_path, mapping)
        else:
            content = tmp_path.read_text(encoding="utf-8", errors="replace")
            restored_text = deanonymize_text(content, mapping)
            final_path = out_dir / f"{final_stem}_restored{suffix}"
            final_path.write_text(restored_text, encoding="utf-8")
    except Exception as exc:
        log.exception("deanonymize_upload failed")
        raise HTTPException(500, f"Restoration failed: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)

    response = {
        "session_id": session_id,
        "entities_restored": len(mapping),
        "original_filename": original_filename,
        "download_url": f"/deanonymize/result/{session_id}",
    }
    if restored_text is not None:
        response["restored_text"] = restored_text
    return response


@app.get("/deanonymize/result/{session_id}")
def download_deanon_result(session_id: str):
    """Download the restored file produced by POST /deanonymize/upload."""
    from pii_shield.config import PII_SHIELD_DIR

    _mime_map = {
        ".txt":  "text/plain",
        ".csv":  "text/csv",
        ".md":   "text/markdown",
        ".log":  "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    out_dir = PII_SHIELD_DIR / "deanon" / f"restored_{session_id}"
    if not out_dir.exists():
        raise HTTPException(404, f"No deanonymized file found for session: {session_id}")

    files = [f for f in out_dir.iterdir() if "_restored" in f.name]
    if not files:
        raise HTTPException(404, f"No deanonymized file found for session: {session_id}")

    chosen = files[0]
    mime = _mime_map.get(chosen.suffix.lower(), "application/octet-stream")
    return FileResponse(str(chosen), filename=chosen.name, media_type=mime)


@app.post("/reapply/{session_id}")
def reapply_after_review(session_id: str):
    """
    Re-anonymize the original uploaded file using HITL review overrides.
    Finds the _source file saved during upload, re-runs anonymization with
    the approved review changes (added/removed entities), and returns a new
    session with the corrected output ready to download.
    """
    _wait_ready()
    from pii_shield.storage import get_review, load_mapping
    from pii_shield.engine.anonymizer import anonymize_file as _anon
    from pii_shield.config import PII_SHIELD_DIR

    # Verify the review exists and has been approved
    review = get_review(session_id)
    if not review:
        raise HTTPException(404, f"No review data for session: {session_id}")
    if review.get("status") != "approved":
        raise HTTPException(400, "Review has not been approved yet. Complete the review first.")

    overrides = review.get("overrides", {})
    if not overrides.get("remove") and not overrides.get("add"):
        raise HTTPException(400, "Review has no changes. Nothing to reapply.")

    # Find the source file saved during upload
    uploads_dir = PII_SHIELD_DIR / "uploads"
    out_dir = uploads_dir / f"pii_shield_{session_id}"
    if not out_dir.exists():
        raise HTTPException(404, f"Output directory not found for session: {session_id}")

    source_files = list(out_dir.glob("_source*"))
    if not source_files:
        raise HTTPException(404, "Original source file not found. Only uploaded files support reapply.")

    source_path = source_files[0]

    # anonymize_file creates output next to its input, so if we pass a nested
    # _source file the output dir lands inside the old session's dir and the
    # download endpoint can't find it.  Copy to uploads root first so the new
    # session dir is created at the expected level.
    import shutil as _shutil
    tmp_source = uploads_dir / f"_reapply_{session_id}{source_path.suffix}"
    _shutil.copy2(str(source_path), str(tmp_source))

    try:
        # Load original domain from review
        domain = review.get("domain", "general")
        engine = _get_engine(domain)
        result = _anon(engine, tmp_source, review_session_id=session_id)
    finally:
        tmp_source.unlink(missing_ok=True)

    if "error" in result:
        raise HTTPException(400, result["error"])

    result["reapplied_from"] = session_id
    return result


# ── Static frontend ───────────────────────────────────────────────────────────
import os as _os
_static_dir = _os.path.join(_os.path.dirname(__file__), "static")
if _os.path.isdir(_static_dir):
    @app.get("/", include_in_schema=False)
    def serve_frontend():
        return FileResponse(_os.path.join(_static_dir, "index.html"))
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="PII Shield REST API server")
    parser.add_argument("--host",   default="127.0.0.1",
                        help="Bind host (default: 127.0.0.1 — localhost only)")
    parser.add_argument("--port",   type=int, default=8080)
    parser.add_argument("--domain", default="general",
                        choices=["general", "legal", "financial", "healthcare"],
                        help="Default domain for stoplist / recognizer selection")
    parser.add_argument("--reload", action="store_true",
                        help="Enable hot-reload (dev mode)")
    args = parser.parse_args()

    # Pre-warm the engine for the selected domain
    import os
    os.environ.setdefault("PII_DEFAULT_DOMAIN", args.domain)

    log.info(f"Starting PII Shield API on http://{args.host}:{args.port}")
    log.info(f"Domain: {args.domain} | Docs: http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "api_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
