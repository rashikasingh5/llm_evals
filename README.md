# eval-harness

[![eval](https://github.com/rashika510/llm_evals/actions/workflows/eval.yml/badge.svg)](https://github.com/rashika510/llm_evals/actions/workflows/eval.yml)

A small harness for testing LLM pipelines. You give it a file of questions with
expected answers, a function that calls your AI, and it tells you how many came
back right.

It's built for learning how evals work, so everything is short enough to read in
one sitting. If you're new to the codebase, start with
[WALKTHROUGH.md](WALKTHROUGH.md).

## Try it without an API key

```bash
python -m eval_harness.cli run \
    --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer \
    --output results/mine.json

python -m eval_harness.cli compare results/baseline_offline.json results/mine.json
```

`mock_pipeline` is a fake AI that returns memorised answers. It costs nothing
and gives the same result every time, which makes it the right thing to test the
harness itself against. When a real model is involved you can never be sure
whether a change came from your code or from the model having a different day.

## Try it with a real model

Groq is the default. It has a free tier and an OpenAI-compatible API. Put your
key in a `.env` file; it's gitignored and the CLI loads it automatically.

```bash
pip install -r requirements.txt --break-system-packages
echo 'GROQ_API_KEY=gsk_...' >> .env

python -m eval_harness.cli run \
    --dataset examples/golden_set.jsonl \
    --pipeline examples.sample_pipeline:answer \
    --output results/a.json --note "baseline prompt"

# change one thing, then run again
python -m eval_harness.cli run \
    --dataset examples/golden_set.jsonl \
    --pipeline examples.sample_pipeline:answer \
    --output results/b.json --note "shorter system prompt"

python -m eval_harness.cli compare results/a.json results/b.json
```

For Anthropic, swap `groq_call` for `anthropic_call` in
`examples/sample_pipeline.py` and `eval_harness/cli.py`. Both wrappers live in
`examples/llm_clients.py`, so the harness doesn't need to know which provider
you use.

## What's in each file

`dataset.py` reads a `.jsonl` file, one JSON object per line, into `Example`
objects with an id, an input, an expected answer, tags, and the name of a
scorer. It rejects broken JSON, missing fields and duplicate ids up front, so a
typo in your dataset fails immediately instead of becoming a strange number
later on.

`scorers.py` holds the graders. `exact_match` and `contains` do string
comparison. `numeric_tolerance` pulls the last number out of the output, which
handles models that show their working. `json_schema_valid` strips code fences,
parses, and checks the top-level keys. `llm_judge` asks a second model to grade
open-ended answers where no string comparison would work. They all take
`(output, expected)` and return a `ScoreResult`, so the runner can use any of
them without knowing which.

`runner.py` is the loop. For each example it looks up the scorer, starts a
timer, calls your pipeline, stops the timer and records the result. A pipeline
that throws is caught and recorded as a failure with the error message, so one
bad example doesn't kill the run.

`report.py` does the arithmetic and the printing. It counts passes overall and
per tag, and `diff_runs` compares two saved runs to find examples that flipped.
Pass to fail is a regression, fail to pass is a fix.

`provenance.py` records what produced a run and checks whether two runs can
fairly be compared. See below.

`cli.py` gives you `run` and `compare`. Most of it is argument parsing; the real
work is in two functions of about fifteen lines each.

To eval your own system, the only thing you write is a function shaped like
`(input) -> output_str`. Point `--pipeline` at it as `module.path:function_name`.

## The two problems this harness is careful about

Both of these came from real bugs in this repo, and both are the kind that
produce a wrong number without ever producing an error.

### 1. You can't tell why the score changed

An eval score measures two things at once: your system, and your grader. When it
moves, either one could be responsible.

`results/run1.json` and `results/run2.json` are two real runs from before this
was fixed. Two examples went from fail to pass while the model's output stayed
byte-for-byte identical. The pass rate went from 60% to 100% because the scorers
were fixed in between. The AI never improved at all, and nothing in either file
says so.

So every run now records a fingerprint of four things: the dataset file, the
source of `scorers.py`, the model name, and the git commit. `compare` reports
which of them moved:

```
=== What changed between these runs ===
  Scorers        a186f30b6865  ->  500780c89a43

  Exactly one variable moved. The delta below is attributable to it.

  !! SCORERS CHANGED between these runs. A higher pass rate here may mean
     you loosened the grader, not that the system improved.
```

If nothing moved, a difference in the score is just noise. If one thing moved,
that's your explanation. If two or more moved, the number can't tell you
anything, and `compare --require-controlled` exits with an error rather than let
you read meaning into it.

The git commit is recorded but not enforced, because it changes on every commit
and a warning that always fires is a warning you learn to ignore.

### 2. A broken grader isn't a failing answer

Running the same eval three times with nothing changed gave 80%, 100%, 100%. The
80% wasn't the model. The judge had replied:

```
{"score": 8, "reason": "Accurately summarizes the fox and sunset but incorrectly attributes the
```

Score 8, which is a pass. But the reply hit the token limit and stopped
mid-sentence, so `json.loads` threw and the old code recorded score 0, failed.
A passing answer became the worst possible result because the grader ran out of
room to speak.

Three things changed. `ScoreResult` and `ExampleResult` now carry a
`grader_failed` flag, because "the grader said no" and "the grader never
answered" are different events and only the first tells you anything about your
system. Ungraded examples come out of the pass-rate denominator and get reported
separately:

```
Pass rate:    4/4 (100.0%)
...
!! 1 example(s) could not be graded: summary_quality
   These are excluded from the numbers above, which cover 4
   of 5 examples. Fix the grader before trusting them.
```

The per-tag breakdown follows the same rule, so an ungraded example doesn't
quietly show up as `open_ended 0/1` either.

The judge also parses defensively now. It strips code fences, scans for the
first balanced `{...}` so prose around the JSON is tolerated, and retries once.
A truncated reply has no closing brace, so it comes back as ungraded rather than
being guessed at. And the judge gets `max_tokens=2000` instead of 300, which is
what caused the truncation in the first place: reasoning models spend tokens
thinking before they write the verdict.

Finally, `diff_runs` counts a grader breakage as its own category rather than a
regression, so CI doesn't send you off debugging a prompt when the fault is in
the harness.

## CI

`.github/workflows/eval.yml` runs the offline eval on every push and pull
request, then compares it to `results/baseline_offline.json` with
`--require-controlled --fail-on-regression`. It needs no API key and no secrets.

If you change a scorer or the dataset on purpose, CI will fail. That's intended.
Regenerate the baseline in the same commit:

```bash
python -m eval_harness.cli run \
    --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer \
    --output results/baseline_offline.json --note "rebaseline: <why>"
```

The `--note` is your audit trail. Rebaseline commits are where graders quietly
get loosened, so they're worth reading carefully.

## Where to take this next

1. Use a real dataset. Five trivia questions is a fixture, not an eval. Point
   this at a system you care about getting right and write 20-30 examples by
   hand, including the awkward edge cases. Nothing else here matters as much.
2. Run each example several times. The same question produced three different
   summaries across three runs here, so a single run of five examples can't tell
   you much.
3. Test your scorers. `contains("...definitely not Paris", "Paris")` currently
   passes.
4. Check that your LLM judge agrees with you. Hand-grade 20 outputs yourself and
   see how often it matches. If it doesn't, the judge isn't doing anything.
5. Add safety examples: prompt injection, PII, and cases the system should
   refuse. Include cases it should not refuse too, or a model that refuses
   everything will score perfectly.
