"""Freeze and execute the attempts allocated to a local trial launch."""
import json
from collections import Counter
from uuid import uuid4

from fastapi import HTTPException

from . import archive, control_results, draft_delivery, greeting, ordinary_drafts
from .store import database, insert_check, now, update_check


def fruit_records(model, request):
    slots = Counter()
    for case in ordinary_drafts.CASES:
        vector = case["vector"]
        slots[vector] += 1
        number = slots[vector]
        spec = greeting.CheckRequest(revision=request.revision, slot=request.slot, seed=request.seed,
                                     digest=request.digest, prompt_source=case["preset"],
                                     filing_vector=vector, filing_variant=number)
        mail = [(None, subject, body) for subject, body in zip(case["subjects"], case["bodies"], strict=True)]
        record = ordinary_drafts.control_record(model, spec, case, mail, "fruit_sequence")
        draft = {"name": case["name"], "subject": case["subjects"][0]}
        record["variant_metadata"] = draft_delivery.variant_metadata(vector, number, draft, request.revision)
        record["trial_label"] = control_results.LABELS[case["preset"]]
        yield record


def saved_records(plan, model, request, selected):
    if not plan["system_prompt"].strip():
        raise HTTPException(422, "Enter a system prompt for saved replays.")
    for vector in ("v1", "v2", "v3"):
        if selected and vector != selected[0]:
            continue
        if getattr(request, "vector", None) not in (None, vector):
            continue
        group = plan["vectors"][vector]
        slots = [(number, draft, draft_delivery.populated_mail(vector, draft))
                 for number, draft in enumerate(group["variations"][:group["count"]], 1)]
        if not selected:
            slots = [slot for slot in slots if slot[2]]
            if not slots:
                raise HTTPException(422, f"Save at least one email in {vector.upper()} to run the full plan.")
        count = len(slots)
        budget = max(20, plan["repetitions"], 5 * group["count"])
        rounds, extra = divmod(budget, count)
        for position in range(budget):
            cycle, index = divmod(position, count)
            number, draft, mail = slots[index]
            if selected and number != selected[1]:
                continue
            if not mail:
                continue
            # Each trial of a vector gets its own recorded seed (launch seed + queue position
            # within the vector), so repetitions differ and a rerun can use the same seeds.
            spec = greeting.CheckRequest(revision=request.revision, slot=request.slot,
                                         seed=(request.seed + position) % 2**31,
                                         digest=request.digest, prompt_source="draft_control",
                                         mitigation=request.mitigation,
                                         expected=getattr(request, "expected", ""),
                                         filing_vector=vector, filing_variant=number)
            record = ordinary_drafts.replay_record(
                model, spec, mail, plan["system_prompt"], plan["fixed_value"])
            record["variant_metadata"] = draft_delivery.variant_metadata(vector, number, draft, request.revision)
            record.update(repetition=cycle + 1, repetition_total=rounds + int(index < extra))
            yield record


def enqueue(db, plan, request, source, selected=None):
    model = plan["models"][request.slot]
    if not model or not request.digest:
        raise HTTPException(422, "Select an installed model for the trial.")
    records = list(fruit_records(model, request) if source == "fruit" else
                   saved_records(plan, model, request, selected))
    if not records:
        if selected:
            raise HTTPException(422, "Enter a subject or body in Message drafts and save the plan.")
        raise HTTPException(422, "Save at least one email in an active variation.")
    sequence_id = str(uuid4())
    db.execute("INSERT INTO sequence_controls VALUES(?, 'running')", (sequence_id,))
    for position, record in enumerate(records, 1):
        record.update(status="queued", sequence_id=sequence_id, sequence_position=position, sequence_total=len(records))
        insert_check(db, record)
    return sequence_id, [record["id"] for record in records]


def control(db, sequence_id, action):
    db.execute("BEGIN IMMEDIATE")
    state = db.execute("SELECT state FROM sequence_controls WHERE id=?", (sequence_id,)).fetchone()
    if state is None:
        raise HTTPException(404, "Queue unavailable.")
    active = db.execute("""SELECT record FROM checks WHERE status IN ('running','queued','paused')
                        AND json_extract(record,'$.sequence_id')=?""", (sequence_id,)).fetchall()
    if not active or state["state"] == "stopped":
        raise HTTPException(409, "This queue has already finished or stopped.")
    target, pending = {"pause": ("paused", "paused"), "resume": ("running", "queued"),
                       "stop": ("stopped", "stopped")}[action]
    db.execute("UPDATE sequence_controls SET state=? WHERE id=?", (target, sequence_id))
    stopped = []
    for row in active:
        record = json.loads(row["record"])
        if record["status"] == "running":
            continue
        record["status"] = pending
        if action == "stop":
            record.update(ended=now(), error="Stopped by the operator.")
            stopped.append(record)
        update_check(db, record)
    return target, stopped


def run(path, sequence_id):
    def check_stop():
        with database(path) as db:
            state = db.execute("SELECT state FROM sequence_controls WHERE id=?", (sequence_id,)).fetchone()
        if state["state"] == "stopped":
            raise greeting.RunStopped("Stopped by the operator.")

    while True:
        with database(path) as db:
            # Resume and the preceding worker may both arrive here. Claim exactly one attempt.
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM checks WHERE status='running'").fetchone():
                return
            row = db.execute("""SELECT record FROM checks WHERE status='queued'
                             AND json_extract(record,'$.sequence_id')=?
                             ORDER BY json_extract(record,'$.sequence_position') LIMIT 1""", (sequence_id,)).fetchone()
            if row is None:
                return
            record = json.loads(row["record"])
            record.update(status="running", execution_started=now())
            update_check(db, record)
        try:
            greeting.run_check(path, record, check_stop=check_stop)
            if record["prompt_source"] in control_results.LABELS:
                record["control_result"] = control_results.assess(record)
        except Exception as exc:
            record.update(status="failed", error=str(exc) or type(exc).__name__, ended=now())
        with database(path) as db:
            update_check(db, record)
        archive.try_export(path, record)
