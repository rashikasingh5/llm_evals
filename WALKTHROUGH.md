# Understanding this repo

There are about 770 lines here, but the idea is only six. The rest is
bookkeeping.

Work through this with a terminal open. Each exercise is one command. Try to
guess the output before you run it.

## The idea

```python
for example in dataset:
    output = my_pipeline(example.input)
    result = scorer(output, example.expected)
    results.append(result)
```

A list of questions, something that answers them, something that grades the
answers, and a record of what happened. That's an eval.

Each file answers one question about that loop:

* `dataset.py` — where do the questions come from?
* `scorers.py` — how do we grade an answer?
* `runner.py` — how do we run the loop and time it?
* `report.py` — how do we add up and compare results?
* `provenance.py` — what produced this run?
* `cli.py` — how do I type all this on a command line?

If you get lost, ask which of the six you're looking at.

## Following one question through

Here's the first line of `examples/golden_set.jsonl`:

```json
{"id": "capital_france", "input": "What is the capital of France?",
 "expected": "Paris", "tags": ["geography", "easy"], "scorer": "contains"}
```

In words: when asked the capital of France, the answer should contain "Paris".
It's an easy geography question.

`dataset.py` reads that line and turns it into an `Example` object. It also
checks for broken JSON, a missing `input`, and duplicate ids, so a typo in your
dataset fails immediately instead of turning into a mysterious wrong number
later.

`runner.py` sees `"scorer": "contains"` and looks up the `contains` function. It
starts a timer, calls your pipeline with the question, and stops the timer. The
model replies `"The capital of France is **Paris**."`

`scorers.py` grades it. The `contains` scorer lowercases both strings and checks
whether one appears in the other, so capitalisation doesn't matter. It returns
`passed=True, score=1.0`.

`runner.py` bundles all of that into one record: the id, the question, what the
model said, what was expected, pass or fail, the score, and how long it took.

`report.py` counts up the passes and works out the pass rate, both overall and
per tag. Per tag matters because one number hides everything: "geography 2/2,
math 0/1" tells you where to look.

`provenance.py` stamps the run with what produced it. More on that below.

## Exercises

### 1. Watch it run

```bash
python3 -m eval_harness.cli run \
    --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer \
    --output results/exercise1.json
```

`mock_pipeline` is a fake AI that returns memorised answers, so this costs
nothing and needs no API key.

Open `results/exercise1.json`. It has three sections: `meta` (what produced
this), `summary` (the totals), and `results` (one entry per question). Find
`capital_france` and match its fields to the steps above.

### 2. Break a question on purpose

In `examples/golden_set_offline.jsonl`, change the France line's `expected`
from `Paris` to `Lyon`. Run the same command again with
`--output results/exercise2.json`.

You'll get 3/4, and that example will show `"passed": false`. Nothing crashed.
The eval just reported that the AI's answer disagreed with what you wrote down.

Which is the lesson: an eval has no idea what's true. It only knows what you
claimed was correct. Your golden answers are an opinion, and if the opinion is
wrong the eval will confidently report the wrong thing.

Change it back to `Paris` before moving on.

### 3. Find a hole in a scorer

```bash
python3 -c "
from eval_harness.scorers import contains
print(contains('The capital of France is definitely not Paris.', 'Paris'))
"
```

It passes, with a score of 1.0. The model said the opposite of the right answer
and the eval called it correct, because `contains` is just looking for the
letters p-a-r-i-s. It has no idea what "not" means.

Scorers are code, and code has bugs. A scorer that's too generous gives you a
green dashboard and a broken product.

### 4. Same problem, different angle

```bash
python3 -c "
from eval_harness.scorers import json_schema_valid
print(json_schema_valid('{\"name\": \"\", \"age\": \"\"}', {'name': '', 'age': ''}))
"
```

Passes. Valid JSON with the right keys, and it extracted nothing at all. The
scorer checks the shape of the answer, not whether the answer is any good.

### 5. The mistake this repo was built to catch

Run the offline eval twice, changing nothing:

```bash
python3 -m eval_harness.cli run --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer --output results/a.json

python3 -m eval_harness.cli run --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer --output results/b.json

python3 -m eval_harness.cli compare results/a.json results/b.json
```

It reports that nothing changed: same model, same dataset, same scorers.

Now compare the two runs from before any of this existed:

```bash
python3 -m eval_harness.cli compare results/run1.json results/run2.json
```

The pass rate went up 40 points, and it warns that neither run recorded any
provenance, so there's no way to say why.

The warning is right. Those two runs have identical model outputs. The pass rate
rose because the scorers were fixed in between. The AI never improved.

## What's in each file

They're short. Read them in this order.

`dataset.py` (46 lines) reads a `.jsonl` file, one JSON object per line, into a
list of `Example` objects.

`scorers.py` (118 lines) holds five graders. Each takes `(output, expected)` and
returns `ScoreResult(passed, score, reason)`. Because they all share that shape,
the runner can use any of them without knowing which. `SCORER_REGISTRY` at the
bottom maps the name you write in your dataset to the function.

The odd one out is `llm_judge`. For open-ended questions where no string
comparison works, it asks another AI to grade the answer. That works, but a
judge has its own biases and needs checking against your own judgement before
you trust it.

`runner.py` (62 lines) is the loop, plus a timer and a `try/except` so one
crashing example doesn't kill the whole run.

`report.py` (152 lines) does arithmetic and printing. `summarize` counts passes.
`diff_runs` compares two saved runs and finds the examples that flipped:
pass to fail is a regression, fail to pass is a fix.

`provenance.py` (148 lines) records a fingerprint of the dataset, the scorers,
the model and the git commit, then checks whether two runs are comparable.

`cli.py` (127 lines) turns command-line words into function calls. Most of it is
`argparse` boilerplate. The real logic is `cmd_run` and `cmd_compare`, about 15
lines each.

## Provenance

An eval score compares two things: what your AI said, and what your grader
accepts. When the score changes, either side could be responsible.

Say a student's exam score goes from 60% to 100%. Did they study, or did the
teacher hand out an easier exam? If nobody recorded which exam was used, you
can't tell. That's what happened between `run1.json` and `run2.json`.

So each run now records four things that could have moved: a hash of the
dataset file, a hash of `scorers.py`, the model name, and the git commit.

A hash is a short code computed from a file's contents, like `84d0ee98e7c1`.
Change one character in the file and the code changes completely. It's a cheap
way to ask "is this the same file as before?"

`compare` then counts how many of those four moved. If none did, any difference
in the score is noise. If one did, that's your explanation. If two or more did,
the comparison can't tell you anything, and `--require-controlled` will exit
with an error rather than let you read meaning into it.

It's the same discipline as any experiment: change one thing at a time.

## Skip these for now

`llm_clients.py`, the `argparse` block at the bottom of `cli.py`, `_git_info()`
in `provenance.py`, and `.github/workflows/eval.yml`. All plumbing.

## Check yourself

1. What are the three inputs to an eval?
2. Why does a scorer return a `reason` and not just true or false?
3. Why keep `mock_pipeline` around when you have a real API key?
4. Why isn't a rising pass rate automatically good news?
5. If you change your prompt and add five new examples, then compare the runs,
   why can't you learn anything from the result?
