import json
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ScoreResult:
    passed: bool
    score: float
    reason: str = ""


def exact_match(output: str, expected: Any, input: Any = None) -> ScoreResult:
    ok = str(output).strip() == str(expected).strip()
    return ScoreResult(passed=ok, score=1.0 if ok else 0.0)


def contains(output: str, expected: Any, input: Any = None) -> ScoreResult:
    ok = str(expected).strip().lower() in str(output).lower()
    return ScoreResult(passed=ok, score=1.0 if ok else 0.0)


def numeric_tolerance(tolerance: float = 0.01) -> Callable:
    """
    Pulls the LAST number-looking token out of free-text output and compares
    it to `expected`. Models often show their work ("17 * 24 = 408"), so
    stripping non-digit characters from the whole string is wrong — it
    concatenates every number in the reasoning into garbage. Taking the
    last match handles "the answer is 408" and "= 408." alike.
    """

    def _score(output: str, expected: Any, input: Any = None) -> ScoreResult:
        matches = re.findall(r"-?\d+\.?\d*", str(output))
        if not matches:
            return ScoreResult(passed=False, score=0.0, reason="no number found in output")
        try:
            out_val = float(matches[-1])
            exp_val = float(expected)
        except (ValueError, TypeError):
            return ScoreResult(passed=False, score=0.0, reason="could not parse number")
        diff = abs(out_val - exp_val)
        ok = diff <= tolerance * max(abs(exp_val), 1e-9)
        return ScoreResult(passed=ok, score=1.0 if ok else 0.0, reason=f"diff={diff}")

    return _score


def _strip_markdown_fence(text: str) -> str:
    """Models routinely wrap JSON in ```json ... ``` fences — strip that before parsing."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def json_schema_valid(output: str, expected: Any = None, input: Any = None) -> ScoreResult:
    """Checks output is valid JSON and (optionally) has the same top-level keys as `expected`."""
    try:
        parsed = json.loads(_strip_markdown_fence(output))
    except json.JSONDecodeError as e:
        return ScoreResult(passed=False, score=0.0, reason=f"invalid JSON: {e}")
    if expected and isinstance(expected, dict):
        missing = set(expected.keys()) - set(parsed.keys())
        if missing:
            return ScoreResult(passed=False, score=0.5, reason=f"missing keys: {missing}")
    return ScoreResult(passed=True, score=1.0)


LLM_JUDGE_PROMPT = """You are grading an AI system's output against a rubric.

Input given to the system:
{input}

System's output:
{output}

Expected / reference answer (may be partial or a rubric, not a strict match):
{expected}

Grade the output from 0-10 on correctness and quality relative to the expected
answer. Be strict — do not give partial credit for confident-sounding but
wrong answers. Respond with ONLY a JSON object, no other text:
{{"score": <0-10 integer>, "reason": "<one sentence>"}}
"""


def make_llm_judge(call_fn: Callable[[str], str], pass_threshold: int = 7) -> Callable:
    """
    Returns a scorer that uses an LLM to grade open-ended output.

    `call_fn` is any function shaped (prompt: str) -> response_text: str.
    Deliberately provider-agnostic — pass in a small wrapper around
    Groq, Anthropic, OpenAI, whatever you're using. See
    examples/llm_clients.py for ready-made wrappers.
    """

    def _score(output: str, expected: Any, input: Any = None) -> ScoreResult:
        prompt = LLM_JUDGE_PROMPT.format(input=input, output=output, expected=expected)
        text = call_fn(prompt).strip()
        try:
            parsed = json.loads(text)
            score = int(parsed["score"])
            reason = parsed.get("reason", "")
        except (json.JSONDecodeError, KeyError, ValueError):
            return ScoreResult(passed=False, score=0.0, reason=f"unparseable judge output: {text}")
        return ScoreResult(passed=score >= pass_threshold, score=score / 10.0, reason=reason)

    return _score


SCORER_REGISTRY: dict[str, Callable] = {
    "exact_match": exact_match,
    "contains": contains,
    "numeric_tolerance": numeric_tolerance(),
    "json_schema_valid": json_schema_valid,
}
