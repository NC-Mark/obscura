"""
Localhost-only HITL review web server.

Serves the review UI and handles approve / add / remove entity API calls.
PII never leaves the machine — server only binds to 127.0.0.1.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ..config import REVIEW_PORT
from ..storage import get_review, load_review, save_review

log = logging.getLogger("pii-shield.review")

_server: HTTPServer | None = None
_port: int | None = None

# Locate review_ui.html relative to this file
_UI_PATH: Path | None = None
for _candidate in [
    Path(__file__).parent / "review_ui.html",
    Path(__file__).parent.parent.parent / "review_ui.html",        # server/review_ui.html
    Path(__file__).parent.parent.parent.parent / "server" / "review_ui.html",
]:
    if _candidate.exists():
        _UI_PATH = _candidate
        break

if _UI_PATH is None:
    # Fallback: original location
    _UI_PATH = Path(__file__).parent.parent.parent / "review_ui.html"


class _ReviewHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for the review UI. Localhost only."""

    def log_message(self, fmt, *args):
        pass  # suppress default Apache-style logging

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/review/"):
            sid = path.split("/review/")[1]
            self._serve_review_page(sid)
        elif path.startswith("/api/review/"):
            sid = path.split("/api/review/")[1]
            self._serve_review_data(sid)
        else:
            self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b""

        if "/api/approve/" in path:
            self._handle_approve(path.split("/api/approve/")[1], body)
        elif "/api/remove_entity/" in path:
            self._handle_remove(path.split("/api/remove_entity/")[1], body)
        elif "/api/add_entity/" in path:
            self._handle_add(path.split("/api/add_entity/")[1], body)
        else:
            self.send_error(404)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _serve_review_page(self, session_id: str):
        if not get_review(session_id):
            self._html(f"<h1>Session not found: {session_id}</h1>")
            return
        try:
            self._html(_UI_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._html(f"<h1>review_ui.html not found</h1><p>Searched: {_UI_PATH}</p>")

    def _serve_review_data(self, session_id: str):
        review = get_review(session_id)
        if not review:
            self._json({"error": f"Session not found: {session_id}"}, 404)
            return
        data = {
            "session_id": session_id,
            "original_text": review["original_text"],
            "entities": review["entities"],
            "confirmed": review["confirmed"],
            "status": review["status"],
            "overrides": review["overrides"],
        }
        if "original_html" in review:
            data["original_html"] = review["original_html"]
        self._json(data)

    def _handle_approve(self, session_id: str, body: bytes):
        review = load_review(session_id) or get_review(session_id)
        if not review:
            self._json({"error": "Session not found"}, 404)
            return
        try:
            overrides = json.loads(body) if body else {}
        except json.JSONDecodeError:
            overrides = {}
        review["status"] = "approved"
        review["overrides"] = {
            "remove": overrides.get("remove", []),
            "add":    overrides.get("add", []),
        }
        save_review(session_id, review)

        # ── Learn from removed false positives ───────────────────────────────
        # When a user removes an entity, save its text to the learned stoplist
        # so it won't be detected as PII in future sessions.
        removed_indices = set(overrides.get("remove", []))
        if removed_indices:
            try:
                from ..custom.loader import save_learned_term
                domain = review.get("domain", "general")
                entities = review.get("entities", [])
                seen_texts: set[str] = set()
                for idx in removed_indices:
                    if 0 <= idx < len(entities):
                        term = entities[idx].get("text", "").strip()
                        if term and term.lower() not in seen_texts:
                            save_learned_term(term, domain)
                            seen_texts.add(term.lower())
                if seen_texts:
                    # Reload stoplist on all active engine instances
                    try:
                        from ..engine.core import PIIEngine
                        for eng in PIIEngine._instances.values():
                            if eng._initialized:
                                eng._reload_stoplist()
                    except Exception:
                        pass
            except Exception as e:
                log.warning(f"Failed to save learned terms: {e}")

        self._json({"status": "approved", "session_id": session_id})

    def _handle_remove(self, session_id: str, body: bytes):
        review = load_review(session_id) or get_review(session_id)
        if not review:
            self._json({"error": "Session not found"}, 404)
            return
        try:
            idx = json.loads(body).get("index")
        except (json.JSONDecodeError, TypeError, AttributeError):
            self._json({"error": "Invalid JSON"}, 400)
            return
        if isinstance(idx, int) and 0 <= idx < len(review.get("entities", [])):
            if idx not in review["overrides"]["remove"]:
                review["overrides"]["remove"].append(idx)
                save_review(session_id, review)
        self._json({"ok": True, "overrides": review["overrides"]})

    def _handle_add(self, session_id: str, body: bytes):
        review = load_review(session_id) or get_review(session_id)
        if not review:
            self._json({"error": "Session not found"}, 404)
            return
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            self._json({"error": "Invalid JSON"}, 400)
            return
        text  = data.get("text", "").strip()
        start = data.get("start", -1)
        end   = data.get("end", -1)
        if not text or start < 0 or end <= start:
            self._json({"error": "Need text, start >= 0, end > start"}, 400)
            return
        review["overrides"]["add"].append({
            "text": text, "type": data.get("type", "PERSON"),
            "start": start, "end": end,
        })
        save_review(session_id, review)
        self._json({"ok": True, "overrides": review["overrides"]})


# ── Server lifecycle ──────────────────────────────────────────────────────────

def start_review_server() -> int | None:
    """Start the review server in a background thread. Returns port or None on failure."""
    global _server, _port
    if _server is not None:
        return _port

    for port in [REVIEW_PORT, REVIEW_PORT + 1]:
        try:
            srv = HTTPServer(("127.0.0.1", port), _ReviewHandler)
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            _server = srv
            _port = port
            log.info(f"Review server on http://127.0.0.1:{port}")
            return port
        except OSError:
            continue

    log.error("Could not start review server on any port")
    return None


def get_review_url(session_id: str) -> str | None:
    port = start_review_server()
    if port is None:
        return None
    return f"http://localhost:{port}/review/{session_id}"
