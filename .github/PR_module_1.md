# Module 1: provenance — make eval comparisons attributable

## Why

An eval score measures two things at once: the system, and the grader. If a
saved run doesn't record which grader ran, a change in pass rate can't be
attributed to anything.

This repo already contains a case in point. `results/run1.json` and
`results/run2.json`:

| example | run1 | run2 | model output |
|---|---|---|---|
| `math_simple` | fail | pass | byte-for-byte identical |
| `extract_json` | fail | pass | byte-for-byte identical |

60% → 100%, and the model never changed — the scorers were fixed between runs.
Nothing in either file says so.

## What this adds

`eval_harness/provenance.py` fingerprints what produced each run:

- `dataset_sha256` — hash of the dataset file
- `scorers_sha256` — hash of `scorers.py` source
- `model` — declared by the pipeline via an `eval_meta` attribute
- `harness_git_sha` (+ dirty-tree flag), timestamp, and a free-text `--note`

`compare` then reports which variables moved:

- **none** → any delta is noise
- **exactly one** → the delta is attributable to it
- **two or more** → uncontrolled; `--require-controlled` exits 1

`harness_git_sha` is recorded but deliberately **not** enforced — it changes on
every commit, so enforcing it would mark nearly every comparison uncontrolled
and train you to ignore the warning.

Verified against a deliberately reverted `numeric_tolerance`:

```
=== What changed between these runs ===
  Scorers        a186f30b6865  ->  500780c89a43
  Exactly one variable moved. The delta below is attributable to it.
  !! SCORERS CHANGED between these runs. A higher pass rate here may mean
     you loosened the grader, not that the system improved.
```

## Also in this PR

- `examples/mock_pipeline.py` — canned answers, so the harness runs with no API
  key, no cost, and no model randomness. This is what makes CI possible.
- `.github/workflows/eval.yml` — runs the offline eval on every push/PR and
  compares against a committed baseline with `--require-controlled
  --fail-on-regression`. No secrets needed.
- `examples/golden_set_offline.jsonl` — the 4 non-judge examples, for CI.
- `.env` auto-loading (dependency-free, non-overriding) + `.env.example`.
- Untracked the committed `__pycache__/*.pyc` files; tightened `.gitignore`.
- `LEARNING_PATH.md` — the 10-module roadmap this is step 1 of.

## Backward compatibility

Old runs with no `meta` block still load. `compare` flags them as
"no provenance recorded — unattributable" rather than failing.

## Note on the baseline

When you intentionally change a scorer or the dataset, CI **will** fail. That's
the design. Regenerate `results/baseline_offline.json` in the same commit and
say why in `--note`. Rebaseline commits are exactly where graders get quietly
loosened, so they deserve review.
