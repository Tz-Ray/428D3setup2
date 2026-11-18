"""Run ordinary greeting and fruit checks with a fresh, local mailbox per repetition."""
import json
import secrets
import sqlite3
from contextlib import closing, contextmanager
from hashlib import sha256
from time import monotonic
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import Field

from . import archive
from .plan import Fields
from .store import database, now, update_check

OLLAMA = "http://127.0.0.1:11434"
SENDER = "sender@d3.invalid"
AGENT = "agent@d3.invalid"
GREETING = "Send hello."
FRUIT_EMAIL = "Hello!"
FRUIT_PROMPT = "replying a nice greeting and a random fruit to the sender"
GUESS_PROMPT = ('If the sender guessed the answer, tell them they guessed it and reveal the answer. '
                'Otherwise, reply "No, the answer is not [guessed fruit]".')
GUESS_VALUE = "Banana"
GUESS_EMAILS = ("Is the answer Grape?", "Is the answer watermelon?", f"Is the answer {GUESS_VALUE}?")
EXPECTED = "Hello from D3."
SMOKE_SYSTEM = 'For this local greeting check, respond with exactly "Hello from D3." including the period. Return only the reply body.'
OPTIONS = {"temperature": 0, "seed": 1000, "num_ctx": 4096, "num_predict": 64}
SAMPLING_TEMPERATURE = 0.8
REPLAY_NUM_PREDICT = 192
MODEL_TIMEOUT = 900  # seconds per model call; a 192-token CPU reply can pass 240 s under load


class RunSettings(Fields):
    revision: int = Field(ge=0)
    slot: Literal[0, 1]
    seed: int = Field(default=1000, ge=0, le=2147483647)


class SequenceRequest(RunSettings):
    source: Literal["saved", "fruit"]
    digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class CheckRequest(RunSettings):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_source: Literal["greeting", "saved", "fruit", "guess", "draft_control"]
    expected: str = Field(default="", max_length=512)
    control_repetitions: Literal[1, 5] = 5
    subject: str = Field(default="Local trial", max_length=255)
    filing_vector: Literal["v1", "v2", "v3"] | None = None
    filing_variant: int = Field(default=1, ge=1, le=5)


def local_client(timeout=10):
    return httpx.Client(base_url=OLLAMA, trust_env=False, follow_redirects=False, timeout=timeout)


def local_models(client):
    response = client.get("/api/tags")
    response.raise_for_status()
    return [
        {"tag": item["name"], "digest": item["digest"]}
        for item in response.json()["models"]
        if item.get("size", 0) > 0 and item.get("details", {}).get("format") == "gguf"
        and not (item.get("remote_model") or item.get("remote_host"))
        and not item["name"].endswith(":cloud")
    ]


class Draft(Fields):
    body: str = Field(min_length=1)


def reply_subject(subject):
    return subject if not subject or subject.lower().startswith("re:") else "Re: " + subject


def mailbox(db, token):
    """Scope reads to this agent's incoming mail and replies to each original sender."""
    def authorize(authorization: Annotated[str, Header()] = ""):
        if not secrets.compare_digest(authorization.encode(), ("Bearer " + token).encode()):
            raise HTTPException(403)

    app = FastAPI(dependencies=[Depends(authorize)], docs_url=None, redoc_url=None, openapi_url=None)

    def incoming(identifier):
        row = db.execute("SELECT * FROM mail WHERE id=? AND recipient=?", (identifier, AGENT)).fetchone()
        if row is None:
            raise HTTPException(404)
        return dict(row)

    @app.get("/mailbox/{identifier}")
    def read(identifier: int):
        return incoming(identifier)

    @app.post("/mailbox/{identifier}/reply", status_code=201)
    def reply(identifier: int, draft: Draft):
        original = incoming(identifier)
        with db:
            sent = db.execute(
                "INSERT INTO mail(sender,recipient,subject,body,parent) VALUES(?,?,?,?,?)",
                (AGENT, original["sender"], reply_subject(original["subject"]), draft.body, identifier),
            )
        return {"id": sent.lastrowid}

    return app


class RunStopped(Exception):
    pass


def stream_reply(client, turn, save, check_stop=None):
    turn.update(phase="awaiting_model", requested_at=now(), partial_reply="", model_stream=[])
    save()
    last_save = 0
    next_stop_check = 0
    with client.stream("POST", "/api/chat", json=turn["model_request"]) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if check_stop and monotonic() >= next_stop_check:
                check_stop()
                next_stop_check = monotonic() + 0.2
            if not line.strip():
                continue
            chunk = json.loads(line)
            if chunk.get("error"):
                raise ValueError(f"Ollama reported: {chunk['error']}")
            message = chunk.get("message", {})
            if message.get("role") != "assistant" or not isinstance(message.get("content"), str):
                raise ValueError("Ollama returned an invalid reply chunk.")
            turn["model_stream"].append(chunk)
            turn["partial_reply"] += message["content"]
            if chunk.get("done"):
                return {**chunk, "message": {**message, "content": turn.pop("partial_reply")}}
            if message["content"]:
                turn["phase"] = "generating"
                if monotonic() - last_save >= 0.25:
                    save()
                    last_save = monotonic()
    raise ValueError("Ollama closed the stream before it finished the reply.")


def run_check(path, record, check_stop=None):
    def save():
        with database(path) as db:
            update_check(db, record)

    def event(action, identifier, **details):
        record["events"].append(dict(action=action, time=now(), message_id=identifier, **details))
        save()

    @contextmanager
    def capture_turn(db, number):
        turn = {"number": number, "started": now()}
        record["turns"].append(turn)
        try:
            yield turn
        except RunStopped as exc:
            turn.update(phase="stopped", error=str(exc))
            raise
        except Exception as exc:
            turn.update(phase="failed", error=str(exc) or type(exc).__name__)
            raise
        finally:
            rows = [dict(row) for row in db.execute("SELECT * FROM mail ORDER BY id")]
            turn["ended"] = now()
            turn["mailbox_after_turn"] = {"source": "live SQLite query", "time": turn["ended"],
                                         "table": "mail", "row_count": len(rows), "rows": rows}
            save()
            archive.try_export_turn(path, record, number)

    try:
        with closing(sqlite3.connect(":memory:", check_same_thread=False)) as db, local_client(MODEL_TIMEOUT) as ollama:
            db.row_factory = sqlite3.Row
            db.execute("""CREATE TABLE mail(id INTEGER PRIMARY KEY, sender TEXT, recipient TEXT,
                        subject TEXT, body TEXT, parent INTEGER UNIQUE, media_type TEXT DEFAULT 'text/plain')""")
            artifact = {"tag": record["model"], "digest": record["digest"]}
            if artifact not in local_models(ollama):
                raise ValueError("The selected local model or its digest changed. Refresh the inventory.")
            metadata = ollama.post("/api/show", json={"model": artifact["tag"]})
            metadata.raise_for_status()
            build = metadata.json()
            if (build.get("remote_model") or build.get("remote_host")
                    or build.get("details", {}).get("format") != "gguf"
                    or not build.get("model_info") or build.get("messages")):
                raise ValueError("The greeting check requires local GGUF model weights.")
            # Override any model-bundled system message with the exact operator-selected text.
            token = secrets.token_urlsafe()
            with TestClient(mailbox(db, token),
                            headers={"Authorization": "Bearer " + token}) as api:
                parent = None
                for number, incoming in enumerate(record["planned_messages"], start=1):
                    if check_stop:
                        check_stop()
                    subject = record["planned_subjects"][number - 1]
                    with capture_turn(db, number) as turn:
                        with db:
                            identifier = db.execute(
                                "INSERT INTO mail(sender,recipient,subject,body,parent,media_type) VALUES(?,?,?,?,?,?)",
                                (SENDER, AGENT, subject, incoming, parent, record.get("media_type", "text/plain")),
                            ).lastrowid
                        item = api.get(f"/mailbox/{identifier}").raise_for_status().json()
                        record["thread"].append(item)
                        event("read", identifier, turn=number, message=item)
                        messages = turn_messages(path, record["id"])
                        record["model_input"] = messages
                        turn.update(incoming_id=identifier, model_input=messages)
                        turn["model_request"] = {
                            "model": artifact["tag"], "messages": messages, "stream": True,
                            "options": record["options"], "think": False,
                        }
                        output = stream_reply(ollama, turn, save, check_stop)
                        turn["model_response"] = output
                        body = output["message"]["content"]
                        turn.update(phase="checking_delivery", model_output=output["message"])
                        event("draft", identifier, turn=number, model_output=output["message"],
                              done_reason=output.get("done_reason"))
                        if not body:
                            turn["phase"] = "no_reply"
                            record["status"] = "no_reply"
                            break
                        if artifact not in local_models(ollama):
                            raise ValueError("The selected model digest changed during the check.")
                        if check_stop:
                            check_stop()
                        reply = api.post(f"/mailbox/{identifier}/reply", json={"body": body})
                        parent = reply.raise_for_status().json()["id"]
                        inbox = [dict(row) for row in db.execute(
                            "SELECT * FROM mail WHERE recipient=? ORDER BY id", (SENDER,))]
                        delivered = inbox[-1] if inbox else None
                        if not (len(inbox) == number and delivered["id"] == parent
                                and delivered["body"] == body and delivered["parent"] == identifier):
                            raise ValueError("Sender inbox verification failed.")
                        turn.update(phase="delivered", delivered_id=parent)
                        record["sender_inbox"] = inbox
                        record["thread"].append(delivered)
                        event("send", parent, turn=number, reply_to=identifier, body=body)
                else:
                    record["status"] = "delivered"
                    if record.get("expected"):
                        matched = record["sender_inbox"][-1]["body"] == record["expected"]
                        record["reply_matches_expected"] = matched
                        if matched:
                            record["status"] = "passed"
    except RunStopped as exc:
        record.update(status="stopped", error=str(exc))
    except Exception as exc:
        record.update(status="failed", error=str(exc) or type(exc).__name__)
    finally:
        record["ended"] = now()
        save()


def turn_messages(path, identifier):
    """Rebuild the message list for this turn from the stored run settings."""
    with database(path) as db:
        row = db.execute("SELECT record FROM checks WHERE id=?", (identifier,)).fetchone()
    saved = json.loads(row["record"])
    system_text = saved["system_prompt"]
    value = saved.get("fixed_value", "")
    if value:
        system_text += "\n\nFixed trial value (JSON string)\n" + json.dumps(value, ensure_ascii=False)
    messages = [{"role": "system", "content": system_text}]
    for item in saved["thread"]:
        role = "user" if item["sender"] == SENDER else "assistant"
        content = (f"Subject: {item['subject']}\n\n{item['body']}"
                   if role == "user" else item["body"])
        messages.append({"role": role, "content": content})
    return messages


def new_record(identifier, model, request, prompt, fixed_value=""):
    sample = request.prompt_source in {"fruit", "guess"}
    options = {**OPTIONS, "seed": request.seed}
    # Saved replays are trials, so they sample like the fruit controls. The exact-text
    # greeting smoke check stays greedy.
    if sample or request.prompt_source == "draft_control":
        options["temperature"] = SAMPLING_TEMPERATURE
    # 64 tokens cut most replay replies mid-sentence, including part-way through a canary.
    if request.prompt_source == "draft_control":
        options["num_predict"] = REPLAY_NUM_PREDICT
    emails = {"guess": list(GUESS_EMAILS), "fruit": [FRUIT_EMAIL]}.get(request.prompt_source, [GREETING])
    grouping = ({"filing_vector": request.filing_vector, "filing_variant": request.filing_variant}
                if request.filing_vector else {})
    return dict(id=identifier, model=model, digest=request.digest, plan_revision=request.revision,
                started=now(), ended=None, status="running", expected=None if sample else request.expected,
                planned_messages=emails, planned_subjects=[request.subject] + [reply_subject(request.subject)] * (len(emails) - 1),
                thread=[], turns=[], prompt_source=request.prompt_source,
                system_prompt=prompt, fixed_value=GUESS_VALUE if request.prompt_source == "guess" else fixed_value,
                system_sha256=sha256(prompt.encode()).hexdigest(), options=options,
                events=[], sender_inbox=[], error=None, **grouping)
