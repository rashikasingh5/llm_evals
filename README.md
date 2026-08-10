# eval-harness

![eval](https://github.com/rashika510/eval_harness_base/actions/workflows/eval.yml/badge.svg)

A minimal, real eval harness for LLM pipelines: golden datasets, pluggable
scorers (including LLM-as-judge), run-to-run regression diffing, and
**provenance tracking so a change in pass rate is actually attributable.**

This is the skeleton — it works out of the box on a toy example, and every
piece is meant to be extended. See [LEARNING_PATH.md](LEARNING_PATH.md) for the
roadmap from here to a real eval + guardrails suite.

## The problem this exists to solve

An eval score measures two things at once: your system, and your grader. Here
are two real runs from this repo, `results/run1.json` and `results/run2.json`:

| example | run1 | run2 | model output |
|---|---|---|---|
| `math_simple` | fail | pass | **byte-for-byte identical** |
| `extract_json` | fail | pass | **byte-for-byte identical** |

Pass rate went 60% → 100% and the model never changed. The *scorers* were fixed
between runs. Neither file records which scorers ran, so nothing in the data
says so — you have to already know.

That's what `provenance.py` fixes. Every run now fingerprints the four things
that could have moved, and `compare` tells you which one did.

## Quickstart (no API key needed)

```bash
python -m eval_harness.cli run \
    --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer \
    --output results/mine.json

python -m eval_harness.cli compare results/baseline_offline.json results/mine.json
```

`mock_pipeline` returns canned answers, so this is free, offline, and
deterministic — the right fixture for working on the harness itself.

## Quickstart (real model)

Uses Groq by default (OpenAI-compatible API, free tier available). Put your key
in a `.env` file (already gitignored) — the CLI loads it automatically:

```bash
pip install -r requirements.txt --break-system-packages
echo 'GROQ_API_KEY=gsk_...' >> .env

# Run the sample pipeline against the sample dataset
python -m eval_harness.cli run \
    --dataset examples/golden_set.jsonl \
    --pipeline examples.sample_pipeline:answer \
    --output results/a.json --note "baseline prompt"

# Change ONE thing (a prompt, a model, the dataset), run again
python -m eval_harness.cli run \
    --dataset examples/golden_set.jsonl \
    --pipeline examples.sample_pipeline:answer \
    --output results/b.json --note "shorter system prompt"

# See what changed, and whether the comparison is even valid
python -m eval_harness.cli compare results/a.json results/b.json
```

To use Anthropic instead, swap `groq_call` for `anthropic_call` in
`examples/sample_pipeline.py` and `eval_harness/cli.py` (both wrappers live in
`examples/llm_clients.py`).

## Reading a comparison

```
=== What changed between these runs ===
  Scorers        a186f30b6865  ->  500780c89a43

  Exactly one variable moved. The delta below is attributable to it.

  !! SCORERS CHANGED between these runs. A higher pass rate here may mean
     you loosened the grader, not that the system improved.

=== Regression check ===
Baseline pass rate: 75.0%
New pass rate:      100.0%  (+25.0%)
```

Three outcomes worth knowing:

- **nothing changed** — any delta is run-to-run noise, not a result.
- **exactly one thing changed** — this is the only case where the delta means
  something. That one variable is your explanation.
- **two or more changed** — uncontrolled. The number is not interpretable, and
  `compare --require-controlled` will exit 1 rather than let you believe it.

## How the pieces fit

```
dataset.py     -> loads golden examples (JSONL: id, input, expected, tags, scorer)
runner.py      -> calls YOUR pipeline function on each example, times it, scores it
scorers.py     -> exact_match, contains, numeric_tolerance, json_schema_valid, llm_judge
provenance.py  -> fingerprints what produced a run, and flags invalid comparisons
report.py      -> aggregates a run, and diffs two runs example-by-example
cli.py         -> `run` and `compare` commands
```

The only thing you need to write to eval YOUR system: a function shaped
like `(input) -> output_str`. See `examples/sample_pipeline.py`.
Provider wrappers (Groq, Anthropic) live in `examples/llm_clients.py` —
swap providers there without touching harness code.

## CI

`.github/workflows/eval.yml` runs the offline eval on every push and PR and
compares it to `results/baseline_offline.json` with `--require-controlled
--fail-on-regression`. No API key or secret required.

When you *intentionally* change a scorer or the dataset, CI will fail — that's
the point. Regenerate the baseline in the same commit:

```bash
python -m eval_harness.cli run \
    --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer \
    --output results/baseline_offline.json --note "rebaseline: <why>"
```

The `--note` is the audit trail. "rebaseline" commits are exactly where graders
get quietly loosened, so they're worth reviewing carefully.

## Where to take this next

The full roadmap — 10 modules covering variance, scorer validity, LLM-judge
calibration, cost, guardrails, and drift — lives in
[LEARNING_PATH.md](LEARNING_PATH.md).

Done so far: Module 0 (the scorer-fix illusion, documented above) and
Module 1 (provenance). Next up is Module 2: running each example N times,
because a pass rate from a single run of 5 examples has an error bar wide
enough to hide any change you care about.

The one that actually matters is pointing this at a system you genuinely care
about getting right. Five trivia questions is a fixture, not an eval.
