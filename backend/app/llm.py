"""Thin wrapper around GMI Cloud's OpenAI-compatible endpoint.

All three LLM stages call `complete_json(prompt_name, **vars)` and get a dict back.
"""

from __future__ import annotations

import json
import re

from openai import OpenAI

from .config import GMI_API_KEY, GMI_BASE_URL, GMI_MODEL, PROMPTS

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        if not GMI_API_KEY or not GMI_MODEL:
            raise RuntimeError("set GMI_API_KEY and GMI_MODEL in .env (or add this stage to USE_FIXTURES)")
        _client = OpenAI(base_url=GMI_BASE_URL, api_key=GMI_API_KEY)
    return _client


def load_prompt(name: str, **vars: object) -> str:
    text = (PROMPTS / f"{name}.md").read_text()
    for k, v in vars.items():
        text = text.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, indent=1))
    return text


def complete_json(prompt_name: str, **vars: object) -> dict:
    prompt = load_prompt(prompt_name, **vars)
    resp = client().chat.completions.create(
        model=GMI_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": "You are a short-form video strategist. Reply with JSON only, no prose, no code fences."},
            {"role": "user", "content": prompt},
        ],
    )
    return extract_json(resp.choices[0].message.content or "")


def extract_json(text: str) -> dict:
    """Tolerate code fences or stray prose around the JSON object."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model output: {text[:200]}")
    return json.loads(text[start : end + 1])
