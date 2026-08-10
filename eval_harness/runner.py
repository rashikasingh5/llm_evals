import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from .dataset import Example
from .scorers import ScoreResult


@dataclass
class ExampleResult:
    id: str
    input: Any
    output: str
    expected: Any
    tags: list[str]
    passed: bool
    score: float
    reason: str
    latency_s: float
    error: str | None = None


def run_eval(
    examples: list[Example],
    pipeline: Callable[[Any], str],
    scorer_registry: dict[str, Callable],
    default_scorer: str = "exact_match",
) -> list[ExampleResult]:
    results = []
    for ex in examples:
        scorer_name = ex.scorer or default_scorer
        scorer = scorer_registry.get(scorer_name)
        if scorer is None:
            raise ValueError(f"Unknown scorer '{scorer_name}' for example {ex.id}")

        start = time.time()
        error = None
        output = ""
        try:
            output = pipeline(ex.input)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        latency = time.time() - start

        if error:
            result = ExampleResult(
                id=ex.id, input=ex.input, output="", expected=ex.expected, tags=ex.tags,
                passed=False, score=0.0, reason="pipeline raised an exception",
                latency_s=latency, error=error,
            )
        else:
            score_result: ScoreResult = scorer(output, ex.expected, ex.input)
            result = ExampleResult(
                id=ex.id, input=ex.input, output=output, expected=ex.expected, tags=ex.tags,
                passed=score_result.passed, score=score_result.score, reason=score_result.reason,
                latency_s=latency, error=None,
            )
        results.append(result)
    return results


def results_to_dicts(results: list[ExampleResult]) -> list[dict]:
    return [asdict(r) for r in results]