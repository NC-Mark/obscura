# OBSCURA

**Local document anonymization — use any AI tool on sensitive documents without sensitive data ever reaching the AI.**

Built on top of the excellent [PII Shield](https://github.com/gregmos/PII-Shield) by Grigorii, extended into a full REST API and web application.

---

## The Problem

You want to use AI to help with legal contracts, healthcare records, financial documents, or any other sensitive work. But you can't paste real client data into ChatGPT, Claude, Gemini, or any public LLM — not for privacy reasons, not for compliance, not for client confidentiality.

## The Solution

OBSCURA runs locally on your machine and sits between your documents and the AI:

1. **Anonymize** — upload a document or paste text. OBSCURA replaces names, addresses, emails, phone numbers, account numbers, and other PII with placeholders: `<PERSON_1>`, `<EMAIL_1>`, `<IBAN_1>`, etc.
2. **Work with any AI** — take the anonymized version into ChatGPT, Claude, Copilot, Gemini, your own tool — whatever fits the job. The AI does its work on clean data.
3. **Restore** — bring the AI's output back into OBSCURA. It replaces every placeholder with the original value, based on the session mapping stored locally.

The anonymization and deanonymization happen entirely on your machine. What reaches the AI contains no sensitive data.

---

## Features

- **Web application** — full browser UI, no code required
- **REST API** — documented at `/docs`, callable from any app or script
- **File support** — `.docx`, `.pdf`, `.txt`, `.csv`, `.md`
- **Experts in the loop** — built-in review UI to correct missed or wrongly-flagged entities before finalizing. Domain experts know their data; the tool supports their judgment.
- **Domain profiles** — legal, financial, healthcare. Each profile brings targeted entity recognition, custom stopwords, and regex patterns.
- **Custom stoplist** — suppress terms that should never be anonymized (e.g. company boilerplate, role titles)
- **Session management** — every anonymization session is saved locally. Restore PII days later, after your AI has done its work.
- **Dark / light mode**
- **MCP server** — optional Claude Desktop integration via `mcp_server.py`

---

## NER Engine

Detection is powered by two complementary tools:
- **[Presidio](https://github.com/microsoft/presidio)** (Microsoft) — pattern-based recognition for structured PII (emails, phone numbers, IBANs, NI numbers, passport numbers, etc.)
- **[GLiNER](https://github.com/urchade/GLiNER)** — transformer-based NER for contextual entities (names, organisations, locations)

---

## Quick Start (Windows)

```
1. Double-click install.bat
2. Double-click start.bat
3. Open http://localhost:8080
```

Or manually:

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
py api_server.py
```

Then open `http://localhost:8080`.

API documentation: `http://localhost:8080/docs`

---

## Project Structure

```
server/
├── api_server.py          # REST API (FastAPI) + static file serving
├── mcp_server.py          # Claude Desktop / MCP integration
├── pii_shield/            # Core engine package
│   ├── engine/            # Anonymizer, deanonymizer, NER core
│   ├── storage/           # Session mapping persistence
│   ├── review/            # HITL review server + UI
│   ├── profiles/          # Domain profile management
│   ├── recognizers/       # Custom Presidio recognizers (EU PII)
│   ├── stoplists/         # Domain-specific false-positive suppression
│   └── custom/            # User-defined stopwords and patterns
├── static/
│   └── index.html         # OBSCURA web application (single file)
├── requirements.txt
├── setup.py
├── install.bat            # Windows: create venv + install deps
└── start.bat              # Windows: launch server
```

Runtime data (session mappings, uploaded files, audit logs) is stored at `~/.pii_shield/` and is never committed to this repo.

---

## Credits

Built on [PII Shield](https://github.com/gregmos/pii-shield) by Grigorii Moskalev. Extended into a REST API and web application by Mark Monfort (Head of AI at Madison Marcus / Managing Director at Foundry Labs).
Original engine: GLiNER + Presidio + SpaCy.

---

## License

See `LICENSE`. Original PII Shield codebase retains its original licence. Extensions and modifications are open source — take it, build on it, make it better.
