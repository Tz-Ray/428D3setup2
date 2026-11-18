"""Human-readable local exports from committed, immutable trial records."""
import json
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import control_results, draft_delivery
from .store import database


def folder(record):
    source = record["prompt_source"]
    if "filing_vector" in record:
        group = Path(record["filing_vector"].upper(), f"variant-{record['filing_variant']:02}")
    elif source in control_results.LABELS and not record.get("parent_id"):
        group = Path("calibration", "trial-" + control_results.LABELS[source])
    else:
        group = Path("unassigned")
    started = record.get("parent_started", record["started"])
    stamp = started.split(".")[0].replace("-", "").replace(":", "") + "Z"
    attempt = record.get("parent_id", record["id"])
    directory = group / f"attempt-{stamp}-{attempt}"
    if record.get("parent_id"):
        directory /= f"trial-{record['trial_label']}/repeat-{record['repetition']:02}"
    return Path("trial-logs") / directory


def turn_details(record):
    if record["prompt_source"] == "draft_delivery":
        return
    by_number = {t["number"]: t for t in record.get("turns", [])}
    events = {}
    for event in record["events"]:
        events.setdefault(event.get("turn", 1), []).append(event)
    inbox = {row["id"]: row for row in record["sender_inbox"]}
    observed = {}
    for number in sorted(set(events) | set(by_number)):
        turn = dict(by_number.get(number, {"number": number}))
        turn["events"] = events.get(number, [])
        for event in turn["events"]:
            action, mid = event["action"], event["message_id"]
            if action == "read":
                observed[mid] = event["message"]
            elif action == "send" and mid in inbox:
                observed[mid] = inbox[mid]
            elif action == "draft":
                turn.setdefault("model_output", event["model_output"])
        if not record.get("turns") and number == 1 and "model_input" in record:
            turn["model_input"] = record["model_input"]
        if "mailbox_after_turn" not in turn:
            rows = [observed[mid] for mid in sorted(observed)]
            turn["mailbox_after_turn"] = {
                "source": "reconstructed from recorded reads and verified deliveries",
                "time": None, "table": "mail", "row_count": len(rows), "rows": rows,
            }
        yield turn


def pretty(value):
    return json.dumps(value, indent=2, ensure_ascii=False)


def conversation(record):
    if record["prompt_source"] == "draft_delivery":
        meta = record["variant_metadata"]
        lines = ["Saved draft delivery | local recipient inbox", f"Run ID: {record['id']}",
                 f"Plan revision: {record['plan_revision']}",
                 f"{meta['vector_id'].upper()} · {meta['vector_name']} / Variant {meta['variant_number']} · {meta['variant_name']}"]
        for mail in record["recipient_inbox"]:
            lines.extend(["", f"{mail['stage']} | message {mail['id']} | {mail['delivered_at']}",
                          f"{mail['sender']} → {mail['recipient']}", f"Content-Type: {mail['media_type']}",
                          f"Subject: {mail['subject']}", mail["body"]])
        return "\n".join(lines) + "\n"
    trial = record.get("trial_label") or control_results.LABELS.get(record["prompt_source"], "1")
    metadata = record.get("variant_metadata", {})
    lines = [f"Trial {trial} | {record['prompt_source']} | {record['status']}",
             f"Run ID: {record['id']}", f"Model: {record['model']}", f"Digest: {record['digest']}",
             f"Started: {record['started']}", f"Finished: {record.get('ended') or 'in progress'}",
             f"Plan revision: {record['plan_revision']}", f"Sampling options: {pretty(record['options'])}"]
    if "filing_vector" in record:
        lines.extend([f"Vector: {record['filing_vector'].upper()} · {metadata.get('vector_name', 'unrecorded')}",
                      f"Variant: {record['filing_variant']} · {metadata.get('variant_name') or '(unnamed)'}",
                      f"Authored variant subject: {metadata.get('authored_subject') or '(empty)'}"])
    if record.get("input_source") == "saved_variant":
        lines.append(f"Incoming mail from saved variant | {record['media_type']}")
    if record.get("repetition_total"):
        lines.append(f"Repetition {record['repetition']} of {record['repetition_total']}")
    if "filing_vector" not in record:
        lines.append("Vector / variant: unassigned")
    if record.get("parent_id"):
        lines.append(f"Primary attempt: {record['parent_id']} | Control repetition {record['repetition']}")
    lines.extend(["", "System prompt", record["system_prompt"]])
    if record.get("fixed_value"):
        lines.extend(["", "Fixed trial value", record["fixed_value"]])
    if record.get("controls"):
        lines.extend(["", "Required controls"])
        for slot in record["controls"]:
            lines.append(f"Trial {slot['trial_label']}, repetition {slot['repetition']}: {slot['status']} [{slot['id']}]")
    if record.get("planned_messages"):
        lines.extend(["", "Planned incoming mail"])
        for index, body in enumerate(record["planned_messages"]):
            subject = record["planned_subjects"][index] if "planned_subjects" in record else "(not recorded)"
            lines.extend([f"Question {index + 1} | Subject: {subject or '(empty)'}", body])
    inbox = {item["id"]: item for item in record["sender_inbox"]}
    for turn in turn_details(record):
        lines.extend(["", f"Turn {turn['number']}"])
        for event in turn["events"]:
            action, mid = event["action"], event["message_id"]
            lines.append(f"{event['time']}  {action}  [message {mid}]")
            if action == "read" or (action == "send" and mid in inbox):
                row = event["message"] if action == "read" else inbox[mid]
                lines.extend([f"{row['sender']} → {row['recipient']}",
                              f"Subject: {row.get('subject', '(not recorded)') or '(empty)'}", row["body"]])
            elif action == "draft":
                lines.append(event["model_output"]["content"])
            elif event.get("reason"):
                lines.append(event["reason"])
        if turn.get("model_input"):
            lines.extend(["", "Exact model input (in order)"])
            for message in turn["model_input"]:
                lines.extend([f"[{message['role']}]", message["content"]])
        snapshot = turn["mailbox_after_turn"]
        lines.extend(["", f"Mailbox after turn {turn['number']} | {snapshot['source']}",
                      f"{snapshot['row_count']} rows in {snapshot['table']}", pretty(snapshot["rows"])])
        if turn.get("error"):
            lines.append("Turn error: " + turn["error"])
    if not record["events"]:
        lines.extend(["", "No messages recorded."])
    if record.get("error"):
        lines.extend(["", "Error", record["error"]])
    if record["prompt_source"] in control_results.LABELS:
        lines.extend(["", "Control result", pretty(record.get("control_result") or control_results.assess(record))])
    return "\n".join(lines) + "\n"


def write_atomic(target, content):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as tmp:
        staged = Path(tmp.name)
        try:
            tmp.write(content)
            tmp.flush()
            staged.replace(target)
        finally:
            staged.unlink(missing_ok=True)


def write_turn(directory, record, turn):
    output = directory / f"turn-{turn['number']:02}.json"
    if not output.is_file():
        data = {"run_id": record["id"], "primary_id": record.get("parent_id"),
                "trial_label": record.get("trial_label") or control_results.LABELS.get(record["prompt_source"], "1"),
                "scenario": record["prompt_source"], "model": record["model"], "digest": record["digest"],
                "variant_metadata": record.get("variant_metadata"), **turn}
        write_atomic(output, pretty(data) + "\n")


def try_export_turn(path, record, number):
    try:
        directory = path.parent / folder(record)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        turn = next(t for t in turn_details(record) if t["number"] == number)
        write_turn(directory, record, turn)
    except OSError:
        logging.getLogger(__name__).exception("Could not write turn %s of %s", number, record["id"])


def export(path, record):
    if not record.get("ended"):
        return
    directory = path.parent / folder(record)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    transcript = directory / "conversation.txt"
    structured = directory / "record.json"
    if record["prompt_source"] == "draft_delivery" and "recipient_inbox" not in record:
        if transcript.is_file() and structured.is_file():
            return
        with database(path) as db:
            record = {**record, "recipient_inbox": draft_delivery.recipient_inbox(db, record["id"])}
    if not transcript.is_file():
        write_atomic(transcript, conversation(record))
    turns = list(turn_details(record))
    for turn in turns:
        write_turn(directory, record, turn)
    if not structured.is_file():
        evidence = {**record, "turn_evidence": turns}
        if record["prompt_source"] in control_results.LABELS:
            evidence["control_result"] = record.get("control_result") or control_results.assess(record)
        write_atomic(structured, json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")


def try_export(path, record):
    try:
        export(path, record)
    except OSError:
        logging.getLogger(__name__).exception("Could not write transcript for %s", record["id"])


def reconcile(path):
    # SQLite remains authoritative after interruptions or partial file writes.
    with database(path) as db:
        for row in db.execute("SELECT record FROM checks WHERE status NOT IN ('running','waiting_for_controls')"):
            try_export(path, json.loads(row["record"]))
