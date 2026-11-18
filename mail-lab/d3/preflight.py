"""Run and retain the two ordinary fruit controls before a primary check."""
from uuid import uuid4

from . import greeting
from .control_results import LABELS, assess
from .store import database, insert_check, now, update_check


def schedule(parent, repetitions):
    parent.update(trial_label="1", status="waiting_for_controls", primary_started=None,
                  controls=[{"id": str(uuid4()), "trial_label": label, "preset": preset,
                             "repetition": i + 1, "status": "pending"}
                            for preset, label in LABELS.items() for i in range(repetitions)])


def run(path, parent, spec, export):
    def save():
        with database(path) as db:
            update_check(db, parent)

    try:
        for slot in parent["controls"]:
            preset = slot["preset"]
            request = spec.model_copy(update={"prompt_source": preset,
                                  "seed": (spec.seed + slot["repetition"] - 1) % (2**31)})
            prompt = greeting.FRUIT_PROMPT if preset == "fruit" else greeting.GUESS_PROMPT
            child = greeting.new_record(slot["id"], parent["model"], request, prompt)
            child.update(trial_label=slot["trial_label"], parent_id=parent["id"],
                         parent_started=parent["started"], repetition=slot["repetition"])
            if "variant_metadata" in parent:
                child["variant_metadata"] = parent["variant_metadata"]
            slot["status"] = "running"
            with database(path) as db:
                insert_check(db, child)
                update_check(db, parent)
            greeting.run_check(path, child)
            verdict = assess(child)
            child["control_result"] = verdict
            slot.update(status="passed" if verdict["passed"] else "failed", result=verdict)
            with database(path) as db:
                update_check(db, child)
                update_check(db, parent)
            export(path, child)
            if child["status"] != "delivered":
                break
        if not all(slot["status"] == "passed" for slot in parent["controls"]):
            parent.update(status="skipped", ended=now(), error="Required controls did not all pass.")
            save()
            return
        parent.update(status="running", primary_started=now())
        save()
        greeting.run_check(path, parent)
    except Exception as exc:
        parent.update(status="failed", ended=now(), error=str(exc) or type(exc).__name__)
        save()
