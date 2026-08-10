import json
from pathlib import Path
from typing import Any


def summarize(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    avg_score = sum(r["score"] for r in results) / total if total else 0.0
    avg_latency = sum(r["latency_s"] for r in results) / total if total else 0.0
    errors = [r for r in results if r["error"]]

    by_tag: dict[str, dict] = {}
    for r in results:
        for tag in r["tags"] or ["untagged"]:
            bucket = by_tag.setdefault(tag, {"total": 0, "passed": 0})
            bucket["total"] += 1
            bucket["passed"] += int(r["passed"])

    return {
        "total": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0.0,
        "avg_score": avg_score,
        "avg_latency_s": avg_latency,
        "error_count": len(errors),
        "by_tag": {
            tag: {"total": v["total"], "passed": v["passed"], "pass_rate": v["passed"] / v["total"]}
            for tag, v in by_tag.items()
        },
    }


def save_run(results: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summarize(results), "results": results}
    path.write_text(json.dumps(payload, indent=2, default=str))


def load_run(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def diff_runs(baseline_path: str | Path, new_path: str | Path) -> dict:
    baseline = {r["id"]: r for r in load_run(baseline_path)["results"]}
    new = {r["id"]: r for r in load_run(new_path)["results"]}

    regressions, fixes, common_ids = [], [], set(baseline) & set(new)
    for eid in common_ids:
        b, n = baseline[eid], new[eid]
        if b["passed"] and not n["passed"]:
            regressions.append({"id": eid, "input": n["input"], "was": b["output"], "now": n["output"]})
        elif not b["passed"] and n["passed"]:
            fixes.append({"id": eid})

    only_baseline = set(baseline) - set(new)
    only_new = set(new) - set(baseline)

    b_summary = summarize(list(baseline.values()))
    n_summary = summarize(list(new.values()))

    return {
        "baseline_pass_rate": b_summary["pass_rate"],
        "new_pass_rate": n_summary["pass_rate"],
        "pass_rate_delta": n_summary["pass_rate"] - b_summary["pass_rate"],
        "regressions": regressions,
        "fixes": fixes,
        "examples_only_in_baseline": sorted(only_baseline),
        "examples_only_in_new": sorted(only_new),
    }


def print_summary(summary: dict, title: str = "Run summary") -> None:
    print(f"\n=== {title} ===")
    print(f"Pass rate:    {summary['passed']}/{summary['total']} ({summary['pass_rate']:.1%})")
    print(f"Avg score:    {summary['avg_score']:.2f}")
    print(f"Avg latency:  {summary['avg_latency_s']:.2f}s")
    if summary["error_count"]:
        print(f"Errors:       {summary['error_count']}")
    if summary["by_tag"]:
        print("By tag:")
        for tag, v in summary["by_tag"].items():
            print(f"  {tag:20s} {v['passed']}/{v['total']} ({v['pass_rate']:.1%})")


def print_diff(diff: dict) -> None:
    print(f"\n=== Regression check ===")
    print(f"Baseline pass rate: {diff['baseline_pass_rate']:.1%}")
    print(f"New pass rate:      {diff['new_pass_rate']:.1%}  ({diff['pass_rate_delta']:+.1%})")
    if diff["regressions"]:
        print(f"\n⚠️  {len(diff['regressions'])} REGRESSION(S):")
        for r in diff["regressions"]:
            print(f"  - {r['id']}: was passing, now failing")
            print(f"      now: {str(r['now'])[:120]}")
    if diff["fixes"]:
        print(f"\n✅ {len(diff['fixes'])} example(s) newly fixed")
    if not diff["regressions"] and not diff["fixes"]:
        print("No change in per-example pass/fail.")