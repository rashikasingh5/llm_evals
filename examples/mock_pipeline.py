"""
A fake pipeline with canned answers. No API key, no network, no cost.

Two reasons this exists:

1. Anyone who clones the repo can run the harness end-to-end immediately —
   including CI, which has no API keys.
2. It's deterministic, so when a pass rate changes you know for certain it
   wasn't the model. That makes it the right fixture for testing the harness
   itself.

The canned outputs are real responses copied from a Groq run, quirks and all
(markdown bold, code fences, the × character) — those quirks are exactly what
scorers trip over.
"""

CANNED = {
    "What is the capital of France?": "The capital of France is **Paris**.",
    "What is the capital of Australia?": "The capital of Australia is **Canberra**.",
    "What is 17 * 24?": "17 × 24 = 408.",
    "Extract as JSON with keys name, age from: 'Rashika is 29 years old'":
        '```json\n{\n  "name": "Rashika",\n  "age": 29\n}\n```',
    "Summarize in one sentence: The quick brown fox jumps over the lazy dog while "
    "the sun sets behind the hills, painting the sky orange and purple.":
        "A swift brown fox leaps over a lazy dog as the sunset paints the hillsides "
        "orange and purple.",
}


def answer(input_text: str) -> str:
    key = str(input_text).strip()
    if key not in CANNED:
        raise KeyError(f"mock_pipeline has no canned answer for: {key[:60]!r}")
    return CANNED[key]


answer.eval_meta = {"provider": "mock", "model": "canned-v1"}
