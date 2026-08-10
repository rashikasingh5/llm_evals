"""
Check whether your LLM judge agrees with you.

A judge produces numbers whether or not it is any good, so the numbers on their
own are not evidence. The only way to find out is to grade some outputs
yourself and measure how often the judge reaches the same verdict.

Two numbers come out of this:

- raw agreement: how often judge and human matched
- Cohen's kappa: the same thing, corrected for agreement you'd expect by luck

Kappa matters because raw agreement lies when the labels are lopsided. If 18 of
20 outputs are good, a judge that blindly says "pass" every time scores 90%
agreement while knowing nothing. Kappa scores that judge at 0.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class LabelledOutput:
    id: str
    output: str
    human_label: bool | None
    note: str = ""


def load_labels(path: str | Path) -> list[LabelledOutput]:
    rows = []
    for line_num, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{line_num} — invalid JSON: {e}")
        rows.append(
            LabelledOutput(
                id=row["id"],
                output=row["output"],
                human_label=row.get("human_label"),
                note=row.get("note", ""),
            )
        )
    return rows


def cohens_kappa(pairs: list[tuple[bool, bool]]) -> float:
    """
    Agreement between two raters, corrected for chance.

    1.0 is perfect, 0.0 is no better than guessing at the observed rates, and
    negative means the two disagree more than chance would predict.
    """
    n = len(pairs)
    if n == 0:
        return 0.0
    observed = sum(1 for h, j in pairs if h == j) / n

    h_pass = sum(1 for h, _ in pairs if h) / n
    j_pass = sum(1 for _, j in pairs if j) / n
    # Chance agreement: both say pass, or both say fail, purely by coincidence.
    expected = h_pass * j_pass + (1 - h_pass) * (1 - j_pass)

    if expected == 1.0:
        # Everyone said the same thing about everything; kappa is undefined.
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def run_calibration(
    labels: list[LabelledOutput],
    judge: Callable,
    input_text: Any,
    expected: Any,
) -> dict:
    graded = [l for l in labels if l.human_label is not None]

    rows, pairs, ungraded = [], [], []
    for item in graded:
        result = judge(item.output, expected, input_text)
        if result.grader_failed:
            ungraded.append({"id": item.id, "reason": result.reason})
            continue
        rows.append(
            {
                "id": item.id,
                "note": item.note,
                "human": item.human_label,
                "judge": result.passed,
                "judge_score": round(result.score * 10),
                "judge_reason": result.reason,
                "agree": item.human_label == result.passed,
            }
        )
        pairs.append((item.human_label, result.passed))

    n = len(pairs)
    return {
        "total_in_file": len(labels),
        "labelled": len(graded),
        "compared": n,
        "ungraded": ungraded,
        "agreement": sum(1 for h, j in pairs if h == j) / n if n else 0.0,
        "kappa": cohens_kappa(pairs),
        # Judge says pass, you say fail. The dangerous direction: these are the
        # bad outputs your eval would wave through.
        "false_passes": [r for r in rows if r["judge"] and not r["human"]],
        # Judge says fail, you say pass. Costs you real improvements.
        "false_fails": [r for r in rows if not r["judge"] and r["human"]],
        "rows": rows,
    }


def print_calibration(report: dict) -> None:
    if report["labelled"] < report["total_in_file"]:
        missing = report["total_in_file"] - report["labelled"]
        print(f"\n{missing} of {report['total_in_file']} outputs have no human_label yet.")
        if report["labelled"] == 0:
            print("Nothing to compare. Fill in human_label (true/false) and run again.")
            return
        print(f"Comparing the {report['labelled']} you have labelled.\n")

    print("=== Judge vs you ===")
    print(f"{'id':20s} {'you':6s} {'judge':6s} {'score':6s} agree")
    for r in report["rows"]:
        mark = "yes" if r["agree"] else "NO"
        print(
            f"{r['id']:20s} {'pass' if r['human'] else 'fail':6s} "
            f"{'pass' if r['judge'] else 'fail':6s} {r['judge_score']:>3}/10  {mark}"
        )

    n = report["compared"]
    print(f"\nAgreement:     {report['agreement']:.0%}  ({sum(1 for r in report['rows'] if r['agree'])}/{n})")
    print(f"Cohen's kappa: {report['kappa']:.2f}   {_kappa_verdict(report['kappa'])}")

    if report["false_passes"]:
        print(f"\nJudge passed {len(report['false_passes'])} output(s) you failed:")
        for r in report["false_passes"]:
            print(f"  {r['id']} ({r['note']})")
            print(f"      judge: {r['judge_reason'][:110]}")
    if report["false_fails"]:
        print(f"\nJudge failed {len(report['false_fails'])} output(s) you passed:")
        for r in report["false_fails"]:
            print(f"  {r['id']} ({r['note']})")
            print(f"      judge: {r['judge_reason'][:110]}")
    if report["ungraded"]:
        print(f"\n{len(report['ungraded'])} output(s) the judge could not grade at all:")
        for u in report["ungraded"]:
            print(f"  {u['id']}: {u['reason'][:110]}")


def _kappa_verdict(k: float) -> str:
    if k >= 0.8:
        return "(strong; the judge is close to a stand-in for you)"
    if k >= 0.6:
        return "(moderate; usable, but read the disagreements)"
    if k >= 0.4:
        return "(weak; fix the rubric before trusting scores)"
    if k > 0.0:
        return "(barely better than guessing)"
    return "(no better than guessing — the judge is decoration)"
