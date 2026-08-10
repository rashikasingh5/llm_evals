"""
Thin wrappers around different providers, all shaped (prompt: str) -> str.
This is the only file that needs to change if you switch providers —
runner.py, scorers.py, and cli.py don't know or care which one you use.

Groq is OpenAI-compatible, so it uses the `openai` python package pointed
at Groq's base_url — no separate SDK needed.
"""

import os


def groq_call(model: str = "openai/gpt-oss-120b", max_tokens: int = 300):
    """
    Returns a (prompt) -> str function backed by Groq.

    Model notes (as of mid-2026): llama-3.3-70b-versatile and
    llama-3.1-8b-instant are deprecated on Groq. openai/gpt-oss-120b is a
    solid general-purpose default; openai/gpt-oss-20b is faster/cheaper
    for simpler tasks. Check https://console.groq.com/docs/models for the
    current list if a model name stops working.
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
    )

    def _call(prompt: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content

    return _call


def anthropic_call(model: str = "claude-sonnet-4-6", max_tokens: int = 300):
    """Returns a (prompt) -> str function backed by the Anthropic API."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def _call(prompt: str) -> str:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    return _call
