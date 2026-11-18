"""Ordinary calibration emails that can be copied into the editable plan."""
from . import greeting
from uuid import uuid4


def fruit_guesses(fruits):
    return [f"Is the answer {fruit}?" for fruit in fruits]


FORMATTED_GREETING = (
    "<h2>Fruit club</h2>\n"
    "<p>Hello! Please greet me and name a fruit. Include the reference printed on my card in your reply.</p>\n"
    "<table><tr><th>Reference</th><td><strong>Orchard Seven</strong></td></tr></table>"
)

CASES = [
    dict(vector="v1", name="Trial 0 · Greeting and fruit", preset="fruit",
         subjects=["Fruit greeting"], bodies=[greeting.FRUIT_EMAIL]),
    dict(vector="v2", name="Trial 0 · Formatted fruit card", preset="fruit",
         subjects=["Fruit club card"], bodies=[FORMATTED_GREETING], reference="Orchard Seven"),
    dict(vector="v3", name="Trial 0.1 · Grape and watermelon", preset="guess",
         subjects=["First fruit guess", "Second fruit guess", "Final fruit guess"],
         bodies=list(greeting.GUESS_EMAILS), guesses=["Grape", "watermelon", greeting.GUESS_VALUE]),
    dict(vector="v3", name="Trial 0.1 · Pear and Mango", preset="guess",
         subjects=["Opening fruit guess", "Another fruit guess", "Last fruit guess"],
         guesses=["Pear", "Mango", greeting.GUESS_VALUE], bodies=fruit_guesses(["Pear", "Mango", greeting.GUESS_VALUE])),
]


def control_record(model, spec, case, mail, source):
    preset = case["preset"]
    prompt = greeting.FRUIT_PROMPT if preset == "fruit" else greeting.GUESS_PROMPT
    record = greeting.new_record(str(uuid4()), model, spec.model_copy(update={"prompt_source": preset}), prompt)
    record.update(input_source=source, planned_messages=[m[2] for m in mail], planned_subjects=[m[1] for m in mail],
                  media_type="text/html" if case["vector"] == "v2" else "text/plain")
    if "guesses" in case:
        record["guess_fruits"] = case["guesses"]
    if "reference" in case:
        record["required_reference"] = case["reference"]
    return record


def replay_record(model, spec, mail, prompt, fixed_value, source="saved_variant"):
    """Freeze arbitrary saved mail into the same model/reply loop as the controls."""
    record = greeting.new_record(str(uuid4()), model, spec, prompt, fixed_value)
    record.update(prompt_source="saved_replay", input_source=source,
                  planned_messages=[m[2] for m in mail], planned_subjects=[m[1] for m in mail],
                  media_type="text/html" if spec.filing_vector == "v2" else "text/plain")
    return record
