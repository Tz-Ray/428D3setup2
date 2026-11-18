"""Loopback operator API for the D3 mail harness."""
import fcntl
import json
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import archive, control_results, draft_delivery, greeting, ordinary_drafts, preflight, sequences
from .plan import SavePlan, SingleMailFile, ThreadFile
from .store import database, initialize, insert_check, read_plan, update_check

ROOT = Path(__file__).resolve().parents[1] / "d3-state"
ORIGIN = "http://127.0.0.1:8000"
FRONTEND = ROOT.parent / "frontend" / "dist-d3"


def create_app(root=ROOT, *, static_dir=FRONTEND):
    path = root / "operator.sqlite"
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (root / "service.lock").open("a") as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            initialize(path)
            archive.reconcile(path)
            yield

    app = FastAPI(title="D3 sandbox", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if request.headers.get("host") != "127.0.0.1:8000":
            return JSONResponse({"detail": "Use the loopback address."}, status_code=403)
        origin = request.headers.get("origin")
        if (origin is not None or request.method not in {"GET", "HEAD"}) and origin != ORIGIN:
            return JSONResponse({"detail": "Open the local D3 console."}, status_code=403)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                       "connect-src 'self'; img-src 'self' data:; frame-src 'self'; "
                                       "base-uri 'none'; form-action 'none'; object-src 'none'",
        })
        return response

    def operator(request: Request):
        if not secrets.compare_digest(request.cookies.get("d3_operator", "").encode(), token.encode()):
            raise HTTPException(403, "Open the D3 console to start a local session.")

    @app.post("/api/session", status_code=204)
    def session(response: Response):
        response.set_cookie("d3_operator", token, httponly=True, samesite="strict", path="/api")

    auth = [Depends(operator)]

    @app.get("/api/plan", dependencies=auth)
    def plan():
        with database(path) as db:
            return read_plan(db)

    @app.put("/api/plan", dependencies=auth)
    def save(update: SavePlan):
        with database(path) as db:
            changed = db.execute("UPDATE plan SET content=?, revision=revision+1 WHERE id=1 AND revision=?",
                                 (update.plan.model_dump_json(), update.revision))
            if changed.rowcount != 1:
                raise HTTPException(409, "Another tab saved this plan. Reload the saved plan before editing.")
        return {"revision": update.revision + 1}

    @app.post("/api/plan/import-preview", dependencies=auth)
    def preview_import(document: SavePlan | SingleMailFile | ThreadFile):
        return document.model_dump()

    @app.get("/api/models", dependencies=auth)
    def inventory():
        try:
            with greeting.local_client() as client:
                return {"models": greeting.local_models(client)}
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(503, "Local Ollama inventory is unavailable.") from exc

    @app.get("/api/greeting", dependencies=auth)
    def greeting_info():
        return dict(body=greeting.GREETING, system_prompt=greeting.SMOKE_SYSTEM, expected=greeting.EXPECTED,
                    fruit_prompt=greeting.FRUIT_PROMPT, fruit_email=greeting.FRUIT_EMAIL,
                    guess_prompt=greeting.GUESS_PROMPT, guess_value=greeting.GUESS_VALUE,
                    guess_emails=greeting.GUESS_EMAILS, draft_controls=ordinary_drafts.CASES)

    def run_trial(record, spec):
        if record["status"] == "waiting_for_controls":
            preflight.run(path, record, spec, archive.try_export)
        else:
            greeting.run_check(path, record)
            if record["prompt_source"] in control_results.LABELS:
                record["control_result"] = control_results.assess(record)
                with database(path) as db:
                    update_check(db, record)
        archive.try_export(path, record)

    @app.post("/api/draft-deliveries", status_code=201, dependencies=auth)
    def send_drafts(selection: draft_delivery.DraftSelection):
        with database(path) as db:
            record = draft_delivery.deliver(db, selection)
        archive.try_export(path, record)
        return {"id": record["id"]}

    def reserve(db, revision):
        db.execute("BEGIN IMMEDIATE")
        saved = read_plan(db)
        if saved["revision"] != revision:
            raise HTTPException(409, "Reload the saved plan before running the check.")
        if db.execute("SELECT 1 FROM checks WHERE status IN ('queued','running','paused','waiting_for_controls')").fetchone():
            raise HTTPException(409, "A trial or its controls are already running.")
        return saved

    def queue_trials(db, settings, spec, background, source, selected=None):
        sequence_id, identifiers = sequences.enqueue(db, settings, spec, source, selected)
        background.add_task(sequences.run, path, sequence_id)
        return {"id": identifiers[0], "sequence_id": sequence_id, "count": len(identifiers)}

    @app.post("/api/sequences", status_code=202, dependencies=auth)
    def start_sequence(spec: greeting.SequenceRequest, background: BackgroundTasks):
        with database(path) as db:
            settings = reserve(db, spec.revision)["plan"]
            return queue_trials(db, settings, spec, background, spec.source)

    @app.post("/api/sequences/{identifier}/{action}", dependencies=auth)
    def control_sequence(identifier: UUID, action: Literal["pause", "resume", "stop"], background: BackgroundTasks):
        sequence_id = str(identifier)
        with database(path) as db:
            state, stopped = sequences.control(db, sequence_id, action)
        if action == "resume":
            background.add_task(sequences.run, path, sequence_id)
        for record in stopped:
            background.add_task(archive.try_export, path, record)
        return {"state": state}

    @app.post("/api/checks", status_code=202, dependencies=auth)
    def start(spec: greeting.CheckRequest, background: BackgroundTasks):
        with database(path) as db:
            settings = reserve(db, spec.revision)["plan"]
            model = settings["models"][spec.slot]
            if not model:
                raise HTTPException(422, "Choose an installed model in the plan.")
            if spec.filing_vector:
                group = settings["vectors"][spec.filing_vector]
                if spec.filing_variant > group["count"]:
                    raise HTTPException(422, "Choose an active variant from the saved plan.")
                variant = group["variations"][spec.filing_variant - 1]
            if spec.prompt_source == "draft_control":
                if not spec.filing_vector:
                    raise HTTPException(422, "Select a vector and variant for this control.")
                return queue_trials(db, settings, spec, background, "saved", (spec.filing_vector, spec.filing_variant))
            prompt = {"greeting": greeting.SMOKE_SYSTEM, "fruit": greeting.FRUIT_PROMPT,
                      "guess": greeting.GUESS_PROMPT, "saved": settings["system_prompt"]}[spec.prompt_source]
            if not prompt.strip():
                raise HTTPException(422, "Enter a system prompt.")
            fixed_value = "" if spec.prompt_source in control_results.LABELS else settings["fixed_value"]
            record = greeting.new_record(str(uuid4()), model, spec, prompt, fixed_value)
            if spec.filing_vector:
                record["variant_metadata"] = draft_delivery.variant_metadata(
                    spec.filing_vector, spec.filing_variant, variant, spec.revision)
            if record["prompt_source"] in control_results.LABELS:
                record["trial_label"] = control_results.LABELS[record["prompt_source"]]
            else:
                preflight.schedule(record, spec.control_repetitions)
            insert_check(db, record)
        background.add_task(run_trial, record, spec)
        return {"id": record["id"]}

    @app.get("/api/checks", dependencies=auth)
    def checks():
        with database(path) as db:
            return [dict(row) for row in db.execute("""
                SELECT id, started, status, json_extract(record,'$.prompt_source') AS preset,
                       json_extract(record,'$.trial_label') AS trial_label,
                       json_extract(record,'$.input_source') AS input_source,
                       json_extract(record,'$.parent_id') AS parent_id,
                       json_extract(record,'$.sequence_id') AS sequence_id,
                       (SELECT state FROM sequence_controls
                        WHERE sequence_controls.id=json_extract(checks.record,'$.sequence_id')) AS queue_state,
                       json_extract(record,'$.sequence_position') AS sequence_position,
                       json_extract(record,'$.repetition') AS repetition,
                       json_extract(record,'$.repetition_total') AS repetition_total,
                       json_extract(record,'$.ended') AS ended,
                       json_extract(record,'$.filing_vector') AS filing_vector,
                       json_extract(record,'$.filing_variant') AS filing_variant
                FROM checks ORDER BY started DESC, rowid DESC
            """)]

    @app.get("/api/checks/{identifier}", dependencies=auth)
    def check(identifier: UUID):
        with database(path) as db:
            row = db.execute("SELECT record FROM checks WHERE id=?", (str(identifier),)).fetchone()
            if row is None:
                raise HTTPException(404, "Check unavailable.")
            record = json.loads(row["record"])
            source = record["prompt_source"]
            if source == "draft_delivery":
                record["recipient_inbox"] = draft_delivery.recipient_inbox(db, record["id"])
            if source in control_results.LABELS:
                record["trial_label"] = control_results.LABELS[source]
                if record.get("ended") and "control_result" not in record:
                    record["control_result"] = control_results.assess(record)
        record["log_folder"] = str(archive.folder(record))
        record["available_turns"] = [turn["number"] for turn in archive.turn_details(record)
                                     if turn.get("ended") or record.get("ended")]
        return record

    @app.get("/api/checks/{identifier}/files/{filename}", dependencies=auth)
    def file(identifier: UUID, filename: str):
        turn_match = re.fullmatch(r"turn-(\d{2})\.json", filename)
        if filename not in {"record.json", "conversation.txt"} and not turn_match:
            raise HTTPException(404, "Unknown file.")
        record = check(identifier)
        available = record.pop("available_turns")
        record.pop("log_folder")
        if turn_match:
            number = int(turn_match[1])
            if number not in available:
                raise HTTPException(404, "No completed turn with that number.")
            archive.try_export_turn(path, record, number)
        elif not record.get("ended"):
            raise HTTPException(409, "This trial is still running.")
        try:
            archive.export(path, record)
        except OSError as exc:
            raise HTTPException(503, "Unable to write trial files in the local state folder.") from exc
        output = root / archive.folder(record) / filename
        if not output.is_file():
            raise HTTPException(503, "The local trial file could not be written.")
        return FileResponse(output, media_type="text/plain" if filename == "conversation.txt" else "application/json")

    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="console")
    return app
