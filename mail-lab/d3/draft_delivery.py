"""Deliver a saved variation to a per-attempt local inbox."""
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import Field

from .plan import Fields
from .store import insert_check, now, read_plan, update_check


class DraftSelection(Fields):
    revision: int = Field(ge=0)
    vector: Literal["v1", "v2", "v3"]
    variant: int = Field(ge=1, le=5)


VECTOR_NAMES = {"v1": "Plaintext body", "v2": "Hidden markup", "v3": "Earlier and later messages"}


def stages(vector, draft):
    if vector == "v3":
        for number, mail in enumerate(draft["prior_emails"], 1):
            yield f"Prior email {number}", mail["subject"], mail["body"]
    yield "First message", draft["subject"], draft["body"]
    if vector == "v3":
        yield "Follow-up 1", draft["later_subject"], draft["later_body"]
        for number, mail in enumerate(draft["additional_followups"], 2):
            yield f"Follow-up {number}", mail["subject"], mail["body"]


def populated_mail(vector, draft):
    return [(stage, subject, body) for stage, subject, body in stages(vector, draft) if subject.strip() or body.strip()]


def variant_metadata(vector, number, draft, revision):
    return dict(vector_id=vector, vector_name=VECTOR_NAMES[vector], variant_number=number,
                variant_name=draft["name"], authored_subject=draft["subject"], plan_revision=revision)


def delivery_record(vector, number, draft, revision):
    return dict(id=str(uuid4()), started=now(), status="queued", prompt_source="draft_delivery",
                filing_vector=vector, filing_variant=number, plan_revision=revision,
                variant_metadata=variant_metadata(vector, number, draft, revision))


def deliver(db, selection):
    db.execute("BEGIN IMMEDIATE")
    saved = read_plan(db)
    if saved["revision"] != selection.revision:
        raise HTTPException(409, "The saved plan changed. Reload it before sending.")
    group = saved["plan"]["vectors"][selection.vector]
    if selection.variant > group["count"]:
        raise HTTPException(422, "Choose an active variant from the saved plan.")
    draft = group["variations"][selection.variant - 1]
    messages = populated_mail(selection.vector, draft)
    if not messages:
        raise HTTPException(422, "Enter a subject or body in Message drafts and save the plan.")

    record = delivery_record(selection.vector, selection.variant, draft, selection.revision)
    insert_check(db, record)
    deposit(db, record, messages)
    return record


def deposit(db, record, messages):
    media_type = "text/html" if record["filing_vector"] == "v2" else "text/plain"
    db.executemany(
        """INSERT INTO draft_mail(check_id,stage,delivered_at,sender,recipient,subject,body,media_type)
           VALUES(?,?,?,'sender@d3.invalid','recipient@d3.invalid',?,?,?)""",
        ((record["id"], stage, now(), subject, body, media_type) for stage, subject, body in messages),
    )
    record.update(status="delivered", ended=now())
    update_check(db, record)


def recipient_inbox(db, identifier):
    return [dict(row) for row in db.execute(
        "SELECT * FROM draft_mail WHERE check_id=? AND recipient='recipient@d3.invalid' ORDER BY id",
        (identifier,),
    )]
