import argparse
import importlib
import os
import sys
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    """
    Minimal .env reader — KEY=value lines, '#' comments, optional quotes.

    Deliberately dependency-free and non-overriding: a variable already set in
    the real environment always wins, so `GROQ_API_KEY=... python -m ...` and CI
    secrets behave the way you'd expect.
    """
    f = Path(path)
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ.setdefault(key, value)

from . import provenance
from .dataset import load_dataset
from .report import diff_runs, load_run, print_diff, print_meta, print_summary, save_run, summarize
from .runner import results_to_dicts, run_eval
from .scorers import SCORER_REGISTRY, make_llm_judge


def load_pipeline(spec: str):
    """
    spec is 'module.path:function_name', e.g. 'examples.sample_pipeline:answer'

    Returns (function, meta). A pipeline can describe itself for the run record
    by setting an `eval_meta` dict attribute on the function — see
    examples/sample_pipeline.py. Without it, the run just won't know the model.
    """
    module_path, func_name = spec.split(":")
    module = importlib.import_module(module_path)
    fn = getattr(module, func_name)
    return fn, dict(getattr(fn, "eval_meta", {}))


def build_scorer_registry(use_llm_judge: bool) -> dict:
    registry = dict(SCORER_REGISTRY)
    if use_llm_judge:
        if not os.environ.get("GROQ_API_KEY"):
            print("Set GROQ_API_KEY to use the llm_judge scorer (or edit cli.py to use anthropic_call instead).")
            sys.exit(1)
        try:
            from examples.llm_clients import groq_call
        except ImportError:
            print("openai package not installed — run: pip install openai --break-system-packages")
            sys.exit(1)
        # Judges need far more headroom than the 300-token default: reasoning
        # models spend tokens thinking before they emit the JSON verdict, and a
        # reply cut off mid-JSON is unreadable. That looked like the graded
        # answer failing, which it wasn't.
        registry["llm_judge"] = make_llm_judge(
            groq_call(model="openai/gpt-oss-120b", max_tokens=2000)
        )
    return registry


def cmd_run(args):
    examples = load_dataset(args.dataset)
    pipeline, pipeline_meta = load_pipeline(args.pipeline)
    needs_judge = args.default_scorer == "llm_judge" or any(e.scorer == "llm_judge" for e in examples)
    registry = build_scorer_registry(use_llm_judge=needs_judge)

    meta = provenance.collect(
        dataset_path=args.dataset,
        n_examples=len(examples),
        pipeline_spec=args.pipeline,
        pipeline_meta=pipeline_meta,
        default_scorer=args.default_scorer,
        note=args.note,
    )

    results = run_eval(examples, pipeline, registry, default_scorer=args.default_scorer)
    result_dicts = results_to_dicts(results)
    save_run(result_dicts, args.output, meta=meta)
    print_meta(meta, title=f"Run: {args.output}")
    print_summary(summarize(result_dicts))
    print(f"\nSaved to {args.output}")


def cmd_compare(args):
    diff = diff_runs(args.baseline, args.new)
    print_diff(diff)

    prov = diff["provenance"]
    uncontrolled = not prov["known"] or len(prov["changed"]) > 1
    if args.require_controlled and uncontrolled:
        print("\nExiting 1: --require-controlled was set and this comparison is not controlled.")
        sys.exit(1)
    if diff["regressions"] and args.fail_on_regression:
        sys.exit(1)


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="LLM pipeline eval harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run pipeline against a dataset and save results")
    p_run.add_argument("--dataset", required=True)
    p_run.add_argument("--pipeline", required=True, help="module.path:function_name")
    p_run.add_argument("--output", required=True)
    p_run.add_argument("--default-scorer", default="exact_match", choices=list(SCORER_REGISTRY) + ["llm_judge"])
    p_run.add_argument("--note", default=None, help="free-text label saved with the run, e.g. 'shorter system prompt'")
    p_run.set_defaults(func=cmd_run)

    p_cmp = sub.add_parser("compare", help="Diff two saved runs for regressions")
    p_cmp.add_argument("baseline")
    p_cmp.add_argument("new")
    p_cmp.add_argument("--fail-on-regression", action="store_true", help="exit 1 if any regression found (for CI)")
    p_cmp.add_argument(
        "--require-controlled", action="store_true",
        help="exit 1 unless at most one variable (model/dataset/scorers/harness) changed between the runs",
    )
    p_cmp.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
