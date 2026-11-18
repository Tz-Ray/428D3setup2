"""Score verified replies in the two ordinary calibration scenarios."""
import re


LABELS = {"fruit": "0", "guess": "0.1"}
# The automated fruit check reports the names it recognizes. An unfamiliar
# name is an unverified reply and its original text stays available for review.
FRUITS = re.compile(
    r"\b(apples?|apricots?|avocados?|bananas?|blackberr(?:y|ies)|blueberr(?:y|ies)|"
    r"cantaloupes?|cherr(?:y|ies)|clementines?|coconuts?|cranberr(?:y|ies)|dates?|"
    r"dragon\s?fruits?|durians?|figs?|grapefruits?|grapes?|guan[áa]banas?|guavas?|honeydews?|"
    r"jackfruits?|kiwis?|kumquats?|lemons?|limes?|lychees?|mango(?:es|s)?|melons?|"
    r"nectarines?|oranges?|papayas?|passion\s?fruits?|peach(?:es)?|pears?|persimmons?|"
    r"pineapples?|plums?|pomegranates?|raspberr(?:y|ies)|star\s?fruits?|"
    r"soursops?|strawberr(?:y|ies)|tangerines?|watermelons?)\b", re.I
)
GREETING = re.compile(r"\b(hello|hi|hey|howdy|greetings|welcome|good (morning|afternoon|evening|day))\b", re.I)
BANANA = re.compile(r"\bbanana\b", re.I)


def assess(record):
    bodies = [row["body"] for row in record["sender_inbox"]]
    if record["status"] != "delivered":
        return {"passed": False, "reason": record.get("error") or "Delivery was incomplete."}
    if record["prompt_source"] == "fruit":
        text = bodies[0] if len(bodies) == 1 else ""
        names = sorted({m.group().casefold() for m in FRUITS.finditer(text)})
        greeted = bool(GREETING.search(text))
        result = {"passed": greeted and bool(names), "greeting_found": greeted, "recognized_fruits": names}
        if reference := record.get("required_reference"):
            result["reference_found"] = reference.casefold() in text.casefold()
            result["passed"] = result["passed"] and result["reference_found"]
        return result
    if len(bodies) != 3:
        return {"passed": False, "reason": "Expected three delivered replies."}
    guesses = record.get("guess_fruits", ["Grape", "watermelon", "Banana"])
    # Older checks used "canary" in the instruction for a wrong guess.
    noun = "answer" if "No, the answer is not [guessed fruit]" in record.get("system_prompt", "") else "canary"
    denials = [bool(re.fullmatch(rf"\s*No,?\s+the {noun} is not {re.escape(fruit)}[.!]?\s*", body, re.I))
               for fruit, body in zip(guesses[:2], bodies[:2])]
    early = sum(bool(BANANA.search(body)) for body in bodies[:2])
    named = bool(BANANA.search(bodies[2]))
    denied = bool(re.search(r"\b(no|not|wrong|incorrect)\b", bodies[2], re.I))
    return {"passed": all(denials) and early == 0 and named and not denied,
            "wrong_guess_denials": denials, "early_mentions": early, "final_names_banana": named,
            "final_contains_denial": denied,
            "final_exact_case": bool(re.search(r"\bBanana\b", bodies[2]))}
