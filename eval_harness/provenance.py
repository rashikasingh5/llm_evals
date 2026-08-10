"""
Provenance: record what produced a run, so two runs can be compared honestly.

An eval number is a measurement of two things at once — your system AND your
grader. If a saved run doesn't say which model, which dataset, and which version
of the scorers produced it, then a change in pass rate is unattributable. You
cannot tell "the model got better" from "I loosened the check".

This module collects the fingerprints. `report.diff_runs` uses them to warn when
more than one variable moved between two runs.
"""

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import scorers

SCHEMA_VERSION = 1

# The variables that must be held still for a comparison to mean something —
# all but one of them, which is the thing you're deliberately testing.
#
# harness_git_sha is deliberately NOT in this list: it changes on every commit,
# including commits that touch nothing the eval depends on, so counting it would
# make almost every comparison look "uncontrolled" and train you to ignore the
# warning. It's recorded and displayed, just not enforced.
CONTROLLED_FIELDS = ("dataset_sha256", "scorers_sha256", "model")
INFORMATIONAL_FIELDS = ("harness_git_sha",)


def _sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _git_info() -> dict[str, Any]:
    """Current commit of the harness itself, plus whether the tree is dirty."""
    repo_root = Path(__file__).resolve().parent.parent
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=5,
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root, capture_output=True, text=True, timeout=5,
        )
        if sha.returncode != 0:
            return {"harness_git_sha": None, "harness_git_dirty": None}
        return {
            "harness_git_sha": sha.stdout.strip(),
            # Dirty means uncommitted edits — the sha alone doesn't identify the code.
            "harness_git_dirty": bool(dirty.stdout.strip()),
        }
    except (OSError, subprocess.SubprocessError):
        return {"harness_git_sha": None, "harness_git_dirty": None}


def scorers_fingerprint() -> str:
    """
    Hash of the scorer source code. Bumps whenever you edit any scorer, which is
    exactly when previously-saved runs stop being comparable to new ones.
    """
    return _sha256_text(Path(scorers.__file__).read_text())


def collect(
    dataset_path: str | Path,
    n_examples: int,
    pipeline_spec: str,
    pipeline_meta: dict | None = None,
    default_scorer: str = "exact_match",
    note: str | None = None,
) -> dict[str, Any]:
    """Build the `meta` block that gets saved alongside a run's results."""
    pipeline_meta = dict(pipeline_meta or {})
    meta = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_path": str(dataset_path),
        "dataset_sha256": _sha256_file(dataset_path),
        "n_examples": n_examples,
        "scorers_sha256": scorers_fingerprint(),
        "default_scorer": default_scorer,
        "pipeline_spec": pipeline_spec,
        # Whatever the pipeline chose to declare about itself — model, temperature, etc.
        "pipeline": pipeline_meta,
        "model": pipeline_meta.get("model"),
        "note": note,
    }
    meta.update(_git_info())
    return meta


def describe_changes(baseline_meta: dict | None, new_meta: dict | None) -> dict[str, Any]:
    """
    Compare two runs' provenance and report which variables moved.

    Returns {"known": bool, "changed": [field, ...], "warnings": [str, ...]}.
    A comparison is trustworthy when exactly one field changed: that field is
    then the only candidate explanation for a change in pass rate.
    """
    warnings: list[str] = []

    if not baseline_meta or not new_meta:
        which = []
        if not baseline_meta:
            which.append("baseline")
        if not new_meta:
            which.append("new")
        warnings.append(
            f"No provenance recorded for: {', '.join(which)}. "
            "This run predates provenance tracking — any difference is unattributable."
        )
        return {"known": False, "changed": [], "warnings": warnings}

    changed = [f for f in CONTROLLED_FIELDS if baseline_meta.get(f) != new_meta.get(f)]
    also_changed = [f for f in INFORMATIONAL_FIELDS if baseline_meta.get(f) != new_meta.get(f)]

    if "scorers_sha256" in changed:
        warnings.append(
            "SCORERS CHANGED between these runs. A higher pass rate here may mean "
            "you loosened the grader, not that the system improved."
        )
    if "dataset_sha256" in changed:
        warnings.append(
            "DATASET CHANGED between these runs. Pass rates over different question "
            "sets are not comparable."
        )
    if len(changed) > 1:
        warnings.append(
            f"{len(changed)} variables moved at once ({', '.join(changed)}). "
            "This comparison is uncontrolled — you cannot attribute the delta to any one of them."
        )
    for meta, label in ((baseline_meta, "baseline"), (new_meta, "new")):
        if meta.get("harness_git_dirty"):
            warnings.append(
                f"The {label} run was produced from a dirty git tree — its commit sha "
                "does not fully identify the code that ran."
            )

    return {"known": True, "changed": changed, "also_changed": also_changed, "warnings": warnings}
