# Understanding your own repo

You don't need to understand 773 lines. You need to understand about 60. The
rest is bookkeeping around those 60.

Work through this with a terminal open. Every exercise is one command. Try to
**predict the output before you run it** — that's where the learning actually
happens.

---

## Part 1: The entire idea, in 6 lines

Strip away every file in this repo and here is what's left:

```python
for example in dataset:                          # a list of questions
    output = my_pipeline(example.input)          # ask the AI
    result = scorer(output, example.expected)    # is the answer OK?
    results.append(result)                       # write it down
```

That's an eval. A list of questions, a thing that answers them, a thing that
grades the answers, and a record of what happened.

Everything else in this repo exists to answer one of four follow-up questions:

| question | file that answers it |
|---|---|
| where do the questions come from? | `dataset.py` |
| how do we grade an answer? | `scorers.py` |
| how do we run the loop and time it? | `runner.py` |
| how do we add up and compare results? | `report.py` |
| what produced this run? | `provenance.py` |
| how do I type all this on a command line? | `cli.py` |

Six files. Each answers exactly one question. If you ever feel lost, come back
to this table and ask "which of these six am I looking at?"

---

## Part 2: Follow one question through the machine

Take the very first line of `examples/golden_set.jsonl`:

```json
{"id": "capital_france", "input": "What is the capital of France?",
 "expected": "Paris", "tags": ["geography", "easy"], "scorer": "contains"}
```

Read that as a sentence: *"When asked the capital of France, the answer should
contain the word Paris. This is an easy geography question."*

Here's its journey:

**Step 1 — `dataset.py` reads it.**
It turns that line of text into a Python object called an `Example`, with five
fields: `id`, `input`, `expected`, `tags`, `scorer`. It also checks for mistakes
you'd otherwise discover much later — broken JSON, a missing `input`, two
examples sharing an `id`.

**Step 2 — `runner.py` runs it.**
It looks at `"scorer": "contains"` and fetches the `contains` function. It
starts a stopwatch, calls `my_pipeline("What is the capital of France?")`, stops
the stopwatch.

The model replies: `"The capital of France is **Paris**."`

**Step 3 — `scorers.py` grades it.**
The `contains` scorer does exactly what it sounds like:

```python
ok = "paris" in "the capital of france is **paris**."   # True
```

Lowercased on both sides, so capitalization doesn't matter. Returns
`passed=True, score=1.0`.

**Step 4 — `runner.py` writes it down.**
It bundles everything into one `ExampleResult`: the id, the input, what the
model said, what was expected, pass/fail, the score, how long it took.

**Step 5 — `report.py` adds it up.**
Counts passes across all examples, computes the pass rate, and also breaks it
down by tag — so you can see "geography: 2/2, math: 0/1" instead of just one
number hiding everything.

**Step 6 — `provenance.py` stamps it.**
Records *what produced this run*: which dataset, which scorers, which model.
This is the newest piece and the one Part 5 is about.

That's the whole system. Every other line is a variation on those six steps.

---

## Part 3: The exercises

### Exercise 1 — Watch the loop run

```bash
python3 -m eval_harness.cli run \
    --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer \
    --output results/exercise1.json
```

No API key, no cost. `mock_pipeline` is a fake AI that returns memorized
answers — useful precisely because it never surprises you.

Now open `results/exercise1.json` in your editor. It has three sections:
`meta` (what produced this), `summary` (the totals), `results` (one entry per
question). **Find the entry for `capital_france` and match each field to a step
in Part 2.**

### Exercise 2 — Break a question on purpose

Open `examples/golden_set_offline.jsonl` and change the France line's
`"expected"` from `"Paris"` to `"Lyon"`. Re-run Exercise 1's command with
`--output results/exercise2.json`.

**Predict first:** what pass rate do you expect?

You should get 3/4. Now look at that example in the JSON: `"passed": false`.
Nothing broke, nothing crashed — the eval simply reported a disagreement
between what the AI said and what you claimed was correct.

**The point:** an eval doesn't know truth. It only knows whether the output
matches *what you wrote down*. Your golden answers are an opinion, and if the
opinion is wrong, the eval confidently reports the wrong thing.

Change `Lyon` back to `Paris` before continuing.

### Exercise 3 — Find the hole in a scorer

Run this:

```bash
python3 -c "
from eval_harness.scorers import contains
print(contains('The capital of France is definitely not Paris.', 'Paris'))
"
```

It passes. Score 1.0.

Sit with that for a second. The model said the *opposite* of the right answer
and your eval called it correct. `contains` just looks for the letters
p-a-r-i-s anywhere in the text; it has no idea what "not" means.

**The point:** scorers are code, and code has bugs. A scorer that's too
generous gives you a green dashboard and a broken product. This is Module 3 in
the learning path, and it's the most underrated idea in evals.

### Exercise 4 — Watch the same output get graded two different ways

```bash
python3 -c "
from eval_harness.scorers import json_schema_valid
out = '{\"name\": \"\", \"age\": \"\"}'
print(json_schema_valid(out, {'name': '', 'age': ''}))
"
```

Passes. Valid JSON, correct keys — and it extracted absolutely nothing. Same
lesson as Exercise 3 from a different angle: the scorer checks the *shape* of
the answer, not whether the answer is any good.

### Exercise 5 — The mistake this repo was built to catch

Run the offline eval twice with no changes:

```bash
python3 -m eval_harness.cli run --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer --output results/a.json

python3 -m eval_harness.cli run --dataset examples/golden_set_offline.jsonl \
    --pipeline examples.mock_pipeline:answer --output results/b.json

python3 -m eval_harness.cli compare results/a.json results/b.json
```

It says **"nothing changed"** — same model, same dataset, same scorers. Good.

Now compare your two original runs, from before any of this existed:

```bash
python3 -m eval_harness.cli compare results/run1.json results/run2.json
```

It says the pass rate went up 40 points, and warns that **neither run recorded
any provenance**, so the improvement is unattributable.

That warning is correct, and it's the whole reason Module 1 exists. Those two
runs have byte-for-byte identical model outputs. The pass rate rose because the
*scorers* were fixed between them — the AI never improved at all.

---

## Part 4: What each file actually contains

Read them in this order. They're short.

**`dataset.py` (46 lines)** — reads a `.jsonl` file (one JSON object per line)
into a list of `Example` objects, and refuses to continue if the file is
malformed or has duplicate ids. Fail loudly and early; a typo in your dataset
should not become a mysterious wrong number three steps later.

**`scorers.py` (118 lines)** — five graders. Each one is a function taking
`(output, expected)` and returning `ScoreResult(passed, score, reason)`.
Because they all share that shape, the runner can use any of them without
knowing which. `SCORER_REGISTRY` at the bottom is just a dictionary mapping the
name you write in your dataset to the actual function.

The interesting one is `llm_judge`: for open-ended questions where no string
comparison works, it asks *another AI* to grade the answer. Powerful and
genuinely unreliable — that's Module 4.

**`runner.py` (62 lines)** — the loop from Part 1, plus two things: a stopwatch,
and a `try/except` so that one crashing example doesn't kill the whole run (it's
recorded as a failure with the error message).

**`report.py` (152 lines)** — arithmetic and printing. `summarize` counts passes
overall and per tag. `diff_runs` compares two saved runs and finds examples that
flipped: pass→fail is a **regression**, fail→pass is a **fix**. The rest formats
it for the terminal.

**`provenance.py` (148 lines)** — the newest piece. Records a fingerprint of the
dataset, the scorers, the model, and the git commit, then checks whether two
runs are actually comparable.

**`cli.py` (127 lines)** — turns command-line words into function calls. Almost
all of it is `argparse` boilerplate; the real logic is two functions,
`cmd_run` and `cmd_compare`, each about 15 lines.

---

## Part 5: Provenance, explained properly

This is the part that probably felt like it came out of nowhere.

**The problem.** An eval score is a comparison between two things: what your AI
said, and what your grader accepts. When the score changes, either side could
have moved.

Think of a student's exam score going from 60% to 100%. Did the student study,
or did the teacher hand out an easier exam? If nobody wrote down which exam was
used, that question can never be answered.

That is literally what happened in your `run1.json` → `run2.json`. Same
answers, easier grading, and no record of it.

**The fix.** Every run now writes down four things that could have changed:

| what | how it's stored |
|---|---|
| the dataset | a hash of the file |
| the graders | a hash of `scorers.py` |
| the model | the name, e.g. `openai/gpt-oss-120b` |
| the harness code | the git commit |

A **hash** is a short code computed from a file's contents, like
`84d0ee98e7c1`. Change one character in the file and the code changes
completely. It's a fingerprint for files — a cheap way to ask "is this the
exact same file as before?" without storing the whole thing.

**The rule.** `compare` checks how many of those four moved:

- **zero** → any difference is random noise, not a result
- **one** → that one thing is your explanation. This is the only useful case.
- **two or more** → uncontrolled; the number can't be attributed to anything

This is just the scientific method: change one variable at a time. Obvious in a
chemistry lab, and almost nobody does it when tweaking prompts.

---

## What to ignore for now

Genuinely skip these until you need them. They're plumbing:

- `llm_clients.py` — boilerplate for talking to Groq/Anthropic
- the `argparse` block at the bottom of `cli.py`
- `_git_info()` in `provenance.py`
- `.github/workflows/eval.yml` — CI. Useful, but it's GitHub configuration,
  not eval knowledge.

---

## How to know you've understood it

You've got it when you can answer these without looking:

1. What are the three inputs to an eval? *(dataset, pipeline, scorer)*
2. Why does a scorer return a `reason` and not just true/false?
3. Why does `mock_pipeline` exist when you have a real API key?
4. Why is a rising pass rate not automatically good news?
5. If you change your prompt **and** add 5 new examples, then compare — why is
   the result meaningless?

If #5 makes immediate sense, you understand this repo better than most people
shipping AI features, and you're ready for Module 2.
