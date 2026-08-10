# eval-harness

![eval](https://github.com/rashika510/eval_harness_base/actions/workflows/eval.yml/badge.svg)

A small eval harness for LLM pipelines. Golden datasets, pluggable scorers
including LLM-as-judge, run-to-run regression diffing, and provenance tracking
so you can tell what caused a change in the score.

New here? Start with [WALKTHROUGH.md](WALKTHROUGH.md).

## Why provenance

An eval score measures two things at once: your system, and your grader. Two
real runs in this repo, `results/run1.json` and `results/run2.json`, show why
that matters. Two examples went from fail to pass while the model output stayed
byte-for-byte identical. The pass rate went from 60% to 100% because the
scorers were fixed in between, not because anything improved.

Neither file records which scorers ran, so nothing in the data tells you that.
You have to already know. `provenance.py` fixes it: every run now fingerprints
the things that could have moved, and `compare` tells you which one did.

## Quickstart (no API key needed)

```bash
python -m eval_harness.cli run \
    --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer \
    --output results/mine.json

python -m eval_harness.cli compare results/baseline_offline.json results/mine.json
```

`mock_pipeline` returns canned answers, so this is free, offline, and gives the
same result every time. That makes it the right thing to test the harness
against.

## Quickstart (real model)

Uses Groq by default, which has a free tier and an OpenAI-compatible API. Put
your key in a `.env` file. It's gitignored, and the CLI loads it for you.

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

There are three cases. If nothing changed, a difference in the score is just
noise. If exactly one thing changed, that's your explanation. If two or more
changed, the number can't tell you anything, and `compare --require-controlled`
exits with an error instead of letting you read meaning into it.

## How the pieces fit

```
dataset.py     -> loads golden examples (JSONL: id, input, expected, tags, scorer)
runner.py      -> calls YOUR pipeline function on each example, times it, scores it
scorers.py     -> exact_match, contains, numeric_tolerance, json_schema_valid, llm_judge
provenance.py  -> fingerprints what produced a run, and flags invalid comparisons
report.py      -> aggregates a run, and diffs two runs example-by-example
cli.py         -> `run` and `compare` commands
```

To eval your own system, the only thing you have to write is a function shaped
like `(input) -> output_str`. See `examples/sample_pipeline.py`. Provider
wrappers for Groq and Anthropic live in `examples/llm_clients.py`, so you can
switch providers without touching the harness.

## CI

`.github/workflows/eval.yml` runs the offline eval on every push and PR and
compares it to `results/baseline_offline.json` with `--require-controlled
--fail-on-regression`. No API key or secret required.

If you change a scorer or the dataset on purpose, CI will fail. That's intended.
Regenerate the baseline in the same commit:

```bash
python -m eval_harness.cli run \
    --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer \
    --output results/baseline_offline.json --note "rebaseline: <why>"
```

The `--note` is your audit trail. Rebaseline commits are where graders quietly
get loosened, so they're worth a careful read.

## Where to take this next

1. Use a real dataset. Five trivia questions is a fixture, not an eval. Point
   this at a system you care about getting right and write 20-30 examples by
   hand, including the awkward edge cases. Nothing else here matters as much.
2. Run each example several times. LLMs give different answers to the same
   question, and one run of five examples can't tell you much.
3. Test your scorers. `contains("...not Paris", "Paris")` currently passes.
4. Check that your LLM judge agrees with you. Hand-grade 20 outputs yourself and
   see how often it matches. If it doesn't, the judge isn't doing anything.
5. Add safety examples: prompt injection, PII, and cases the system should
   refuse. Include cases it should not refuse too, or a model that refuses
   everything will score perfectly.
