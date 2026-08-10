import json
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ScoreResult:
    passed: bool
    score: float
    reason: str = ""
    # True when the grader itself failed, rather than the system under test.
    # A judge whose reply got truncated tells you nothing about the output it
    # was grading, so counting it as a failing answer is simply wrong.
    grader_failed: bool = False


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

Grade the output from 0-10. Judge it on all of the following:

- Correctness: does it match the expected answer, with no invented or altered
  details?
- Instruction-following: does it obey the constraints in the input, including
  length, format, and the language the input was written in?
- Conciseness: is it as short as the task asked for, with no padding?

Be strict. Do not give partial credit for confident-sounding but wrong answers,
and do not pass an output that is accurate but ignores what was asked for.
Respond with ONLY a JSON object, no other text:
{{"score": <0-10 integer>, "reason": "<one sentence>"}}
"""


def _extract_json_object(text: str) -> dict | None:
    """
    Pull a JSON object out of a judge's reply.

    Judges wrap their answer in prose or code fences, and a reply that hits the
    token limit gets cut off mid-string. Scanning for the first balanced {...}
    recovers the common cases; a truncated reply has no closing brace and
    correctly returns None instead of a wrong score.
    """
    text = _strip_markdown_fence(text)
    start = text.find("{")
    if start == -1:
        return None
    depth, in_string, escaped = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def make_llm_judge(
    call_fn: Callable[[str], str], pass_threshold: int = 7, retries: int = 1
) -> Callable:
    """
    Returns a scorer that uses an LLM to grade open-ended output.

    `call_fn` is any function shaped (prompt: str) -> response_text: str.
    Deliberately provider-agnostic — pass in a small wrapper around
    Groq, Anthropic, OpenAI, whatever you're using. See
    examples/llm_clients.py for ready-made wrappers.

    An unreadable reply is reported as `grader_failed`, NOT as a failing answer.
    Those are different events and conflating them makes your system look worse
    than it is: a judge whose reply was cut off never rendered a verdict at all.
    """

    def _score(output: str, expected: Any, input: Any = None) -> ScoreResult:
        prompt = LLM_JUDGE_PROMPT.format(input=input, output=output, expected=expected)
        last_text = ""
        for attempt in range(retries + 1):
            try:
                last_text = call_fn(prompt).strip()
            except Exception as e:
                last_text = f"{type(e).__name__}: {e}"
                continue
            parsed = _extract_json_object(last_text)
            if parsed is None or "score" not in parsed:
                continue
            try:
                score = int(parsed["score"])
            except (TypeError, ValueError):
                continue
            score = max(0, min(10, score))
            return ScoreResult(
                passed=score >= pass_threshold,
                score=score / 10.0,
                reason=parsed.get("reason", ""),
            )
        return ScoreResult(
            passed=False,
            score=0.0,
            reason=f"judge did not return a usable score after {retries + 1} attempt(s): {last_text[:200]}",
            grader_failed=True,
        )

    return _score


SCORER_REGISTRY: dict[str, Callable] = {
    "exact_match": exact_match,
    "contains": contains,
    "numeric_tolerance": numeric_tolerance(),
    "json_schema_valid": json_schema_valid,
}
