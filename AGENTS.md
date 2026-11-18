# 428 Mail Experiment — instructions for Codex

## Goal
A local email sender/receiver app (not a Gmail-style client) plus an LLM agent that
reads and replies to emails inside the app. You (Codex) build the app and oversee
the agent: run it, read its action log, and judge its replies.

- Backend: FastAPI + SQLite
- Frontend: Vue 3 (Vite)
- Agent model: Meta Llama 3.1 8B Instruct, Q4_K_M, via Ollama
  (tag `llama3.1:8b-instruct-q4_K_M`), plus Qwen 2.5 3B Instruct, Q4_K_M
  (tag `qwen2.5:3b-instruct-q4_K_M`) as the second model

## Hard constraints
- Email is local only. "Sending" stores a message for a local recipient in SQLite.
  No SMTP/IMAP to the internet, no external email providers, no real addresses.
- Bind every server to 127.0.0.1 only (FastAPI 8000, Vite 5173, Ollama 11434).
- The agent works only through the app's HTTP API with its own mailbox account.
  It never gets raw SQL, shell, or filesystem access.
- Log every agent action (read, draft, send) with timestamp, message id and the
  model output, so it can be reviewed.
- Do not push, deploy, or delete data outside this folder without asking.

## Environment (WSL Ubuntu)
- System Python is 3.8 (too old). Use uv: `uv python install 3.12`, then
  `uv venv --python 3.12` in this folder.
- Node 24 / npm 11 are installed.
- Ollama runs in WSL as a systemd user service (binary in ~/.local/opt/ollama).
  - Start it with `ollama-start` (request escalation; an allow rule runs it
    outside the sandbox without a prompt). Stop it with `ollama-stop`.
  - API: http://127.0.0.1:11434. `ollama list` / `ollama run` work from the sandbox.
  - Ask before pulling or deleting models.
- Background processes started inside the sandbox are killed when that command
  ends. Start a server and test it in the same command, or keep it in a
  persistent terminal session.

## Notes
- Record design decisions in DECISIONS.md and progress in PROGRESS.md.
