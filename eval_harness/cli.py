import argparse
import importlib
import os
import sys

from .dataset import load_dataset
from .report import diff_runs, load_run, print_diff, print_summary, save_run, summarize
from .runner import results_to_dicts, run_eval
from .scorers import SCORER_REGISTRY, make_llm_judge


def load_pipeline(spec: str):
    """spec is 'module.path:function_name', e.g. 'examples.sample_pipeline:answer'"""
    module_path, func_name = spec.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


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
        registry["llm_judge"] = make_llm_judge(groq_call(model="openai/gpt-oss-120b"))
    return registry


def cmd_run(args):
    examples = load_dataset(args.dataset)
    pipeline = load_pipeline(args.pipeline)
    needs_judge = args.default_scorer == "llm_judge" or any(e.scorer == "llm_judge" for e in examples)
    registry = build_scorer_registry(use_llm_judge=needs_judge)

    results = run_eval(examples, pipeline, registry, default_scorer=args.default_scorer)
    result_dicts = results_to_dicts(results)
    save_run(result_dicts, args.output)
    print_summary(summarize(result_dicts), title=f"Run: {args.output}")
    print(f"\nSaved to {args.output}")


def cmd_compare(args):
    diff = diff_runs(args.baseline, args.new)
    print_diff(diff)
    if diff["regressions"] and args.fail_on_regression:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="LLM pipeline eval harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run pipeline against a dataset and save results")
    p_run.add_argument("--dataset", required=True)
    p_run.add_argument("--pipeline", required=True, help="module.path:function_name")
    p_run.add_argument("--output", required=True)
    p_run.add_argument("--default-scorer", default="exact_match", choices=list(SCORER_REGISTRY) + ["llm_judge"])
    p_run.set_defaults(func=cmd_run)

    p_cmp = sub.add_parser("compare", help="Diff two saved runs for regressions")
    p_cmp.add_argument("baseline")
    p_cmp.add_argument("new")
    p_cmp.add_argument("--fail-on-regression", action="store_true", help="exit 1 if any regression found (for CI)")
    p_cmp.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
