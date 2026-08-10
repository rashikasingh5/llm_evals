import json
from pathlib import Path
from typing import Any

from .provenance import describe_changes


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


def save_run(results: list[dict], path: str | Path, meta: dict | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta or {}, "summary": summarize(results), "results": results}
    path.write_text(json.dumps(payload, indent=2, default=str))


def load_run(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def diff_runs(baseline_path: str | Path, new_path: str | Path) -> dict:
    baseline_run, new_run = load_run(baseline_path), load_run(new_path)
    baseline = {r["id"]: r for r in baseline_run["results"]}
    new = {r["id"]: r for r in new_run["results"]}

    # Before comparing numbers, work out whether the comparison is even valid.
    provenance = describe_changes(baseline_run.get("meta"), new_run.get("meta"))

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
        "provenance": provenance,
        "baseline_meta": baseline_run.get("meta") or {},
        "new_meta": new_run.get("meta") or {},
        "baseline_pass_rate": b_summary["pass_rate"],
        "new_pass_rate": n_summary["pass_rate"],
        "pass_rate_delta": n_summary["pass_rate"] - b_summary["pass_rate"],
        "regressions": regressions,
        "fixes": fixes,
        "examples_only_in_baseline": sorted(only_baseline),
        "examples_only_in_new": sorted(only_new),
    }


def print_meta(meta: dict, title: str = "Run provenance") -> None:
    if not meta:
        return
    print(f"\n=== {title} ===")
    dirty = " (DIRTY TREE)" if meta.get("harness_git_dirty") else ""
    print(f"When:     {meta.get('timestamp')}")
    print(f"Model:    {meta.get('model') or 'unknown'}")
    print(f"Pipeline: {meta.get('pipeline_spec')}")
    print(f"Dataset:  {meta.get('dataset_path')}  [{meta.get('dataset_sha256')}]")
    print(f"Scorers:  [{meta.get('scorers_sha256')}]")
    print(f"Harness:  {meta.get('harness_git_sha') or 'not a git repo'}{dirty}")
    if meta.get("note"):
        print(f"Note:     {meta['note']}")


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


def _print_provenance_check(diff: dict) -> None:
    prov = diff.get("provenance") or {}
    changed, warnings = prov.get("changed", []), prov.get("warnings", [])

    print("\n=== What changed between these runs ===")
    if not prov.get("known"):
        print("  unknown — at least one run has no provenance recorded")
    elif not changed:
        print("  nothing — same model, same dataset, same scorers.")
        print("  Any difference in pass rate is run-to-run noise, not a real change.")
    else:
        b, n = diff.get("baseline_meta", {}), diff.get("new_meta", {})
        label = {
            "model": "Model", "dataset_sha256": "Dataset",
            "scorers_sha256": "Scorers", "harness_git_sha": "Harness code",
        }
        for f in changed:
            print(f"  {label.get(f, f):14s} {b.get(f)}  ->  {n.get(f)}")
        if len(changed) == 1:
            print(f"\n  Exactly one variable moved. The delta below is attributable to it.")

    b, n = diff.get("baseline_meta", {}), diff.get("new_meta", {})
    for f in prov.get("also_changed", []):
        print(f"  (fyi) harness commit {b.get(f)} -> {n.get(f)}")

    for w in warnings:
        print(f"\n  !! {w}")


def print_diff(diff: dict) -> None:
    _print_provenance_check(diff)
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