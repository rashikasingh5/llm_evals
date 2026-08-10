"""
This is the seam: any function shaped like (input) -> str plugs into the
harness. Swap this out for your actual system — a prompt call, a RAG
pipeline, your job-apply-agent's extraction step, an agent's final answer,
whatever you're evaluating.

This sample calls Groq (OpenAI-compatible endpoint) so
`python -m eval_harness.cli run` works out of the box once GROQ_API_KEY
is set — no Anthropic key required.
"""

from .llm_clients import groq_call

_call = None


def answer(input_text: str) -> str:
    global _call
    if _call is None:
        _call = groq_call(model="openai/gpt-oss-120b")
    return _call(str(input_text))
