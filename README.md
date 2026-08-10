# eval-harness

A minimal, real eval harness for LLM pipelines: golden datasets, pluggable
scorers (including LLM-as-judge), and run-to-run regression diffing.

This is the skeleton — it works out of the box on a toy example, and every
piece is meant to be extended.

## Quickstart

Uses Groq by default (OpenAI-compatible API, free tier available) — no
Anthropic key needed. To use Anthropic instead, swap `groq_call` for
`anthropic_call` in `examples/sample_pipeline.py` and `eval_harness/cli.py`
(both wrappers live in `examples/llm_clients.py`).

```bash
pip install -r requirements.txt --break-system-packages
export GROQ_API_KEY=gsk_...

# Run the sample pipeline against the sample dataset
python -m eval_harness.cli run \
    --dataset examples/golden_set.jsonl \
    --pipeline examples.sample_pipeline:answer \
    --output results/run1.json

# Make a change (edit a prompt, swap a model, tweak your pipeline), run again
python -m eval_harness.cli run \
    --dataset examples/golden_set.jsonl \
    --pipeline examples.sample_pipeline:answer \
    --output results/run2.json

# See exactly what changed, not just the aggregate pass rate
python -m eval_harness.cli compare results/run1.json results/run2.json
```

## How the pieces fit

```
dataset.py   -> loads golden examples (JSONL: id, input, expected, tags, scorer)
runner.py    -> calls YOUR pipeline function on each example, times it, scores it
scorers.py   -> exact_match, contains, numeric_tolerance, json_schema_valid, llm_judge
report.py    -> aggregates a run, and diffs two runs example-by-example
cli.py       -> `run` and `compare` commands
```

The only thing you need to write to eval YOUR system: a function shaped
like `(input) -> output_str`. See `examples/sample_pipeline.py`.
Provider wrappers (Groq, Anthropic) live in `examples/llm_clients.py` —
swap providers there without touching harness code.

## Where to take this next (roughly in order of value)

1. **Point it at something real.** Swap `sample_pipeline.py` for your
   job-apply-agent's extraction step (job posting text -> structured
   fields). Write ~20-30 golden examples by hand, including edge cases
   (weird formatting, missing fields, non-English postings).
2. **Add a `--fail-on-regression` CI hook.** `compare` already supports
   this flag — wire it into a GitHub Action that runs on every prompt/
   pipeline change and blocks the merge if pass rate drops.
3. **Track cost, not just latency.** `runner.py`'s `ExampleResult` is the
   place — add `input_tokens`/`output_tokens`/`cost_usd` fields, pull them
   from `resp.usage` in your pipeline function or have the runner capture
   them via a return-tuple instead of a bare string.
4. **Add a second LLM-judge rubric dimension.** Right now `llm_judge` gives
   one 0-10 score. Real eval suites often score multiple axes (accuracy,
   tone, safety, format-compliance) — extend `make_llm_judge` to return a
   dict of sub-scores.
5. **Historical tracking, not just pairwise diff.** Append each run's
   summary to a small SQLite table or CSV so you can plot pass-rate over
   time across dozens of runs, not just the last two.
6. **Non-determinism handling.** LLM outputs vary run-to-run. Add an
   option to run each example N times and score the majority/average —
   this is what separates a toy eval script from a production one.

Step 1 is the one that actually matters — evals are only valuable when
they're testing something you genuinely care about getting right.
