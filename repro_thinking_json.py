"""Minimal reproduction: Command A+ with a JSON schema, thinking disabled versus enabled.

Needs only the Cohere SDK and an API key: pip install cohere; set CO_API_KEY.
Uses the public Knowledge Automata prompt and a fictional meeting note.
Prints the structure of each reply; never prints the key.

    python repro_thinking_json.py           # reduced schema (4 fields, no descriptions)
    python repro_thinking_json.py full      # the exact schema Knowledge Automata sends
    python repro_thinking_json.py full-ask-json
        # full schema, plus one line in the system prompt asking for JSON, as the
        # structured outputs docs say a json_object request should
"""

import datetime
import importlib.metadata
import json
import os
import sys
import urllib.request

import cohere

MODEL = "command-a-plus-05-2026"
# Pinned to one commit of the public repo, so the inputs never change under the repro.
RAW = "https://raw.githubusercontent.com/miguelmog10/knowledge-automata/b2cd08a7270a2c310470172595635239e77ce5ef"
PROMPT_URL = f"{RAW}/prompts/project-management/decision-registrar.v1.md"
ARTIFACT_URL = f"{RAW}/examples/sample-project/artifacts/ART-0003-tech-sync-2026-03-17.md"
DRAFT_SCHEMA_URL = f"{RAW}/schemas/core/draft.v1.json"
DECISION_SCHEMA_URL = f"{RAW}/schemas/project-management/decision.v1.json"
ASK_JSON = "Reply with one JSON object that matches the response schema, and nothing else."
# Keywords Knowledge Automata removes before sending (its validators check them afterwards).
REMOVED_KEYWORDS = {"$schema", "$id", "maxLength", "minLength", "minItems", "maxItems"}

REDUCED_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "statement": {"type": "string"},
                "context": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["title", "statement"],
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["content", "evidence"],
}


def fetch(url: str) -> str:
    with urllib.request.urlopen(url) as response:
        return response.read().decode("utf-8")


def reduce_schema(schema: dict) -> dict:
    """Drop annotations and validation-only keywords, as Knowledge Automata does."""
    reduced = {}
    for keyword, value in schema.items():
        if keyword in REMOVED_KEYWORDS or keyword.startswith("x-"):
            continue
        if keyword == "properties":
            reduced[keyword] = {name: reduce_schema(sub) for name, sub in value.items()}
        elif keyword == "items":
            reduced[keyword] = reduce_schema(value)
        else:
            reduced[keyword] = value
    return reduced


def full_schema() -> dict:
    """The draft schema with the decision schema inlined as 'content', then reduced."""
    draft = json.loads(fetch(DRAFT_SCHEMA_URL))
    draft["properties"]["content"] = json.loads(fetch(DECISION_SCHEMA_URL))
    return reduce_schema(draft)


def describe(label: str, response) -> None:
    print(f"\n=== {label} ===")
    print("finish_reason:", response.finish_reason)
    print("usage:", response.usage)
    for index, block in enumerate(response.message.content or []):
        kind = getattr(block, "type", None)
        text = getattr(block, "text", None) or getattr(block, "thinking", None) or ""
        print(f"[{index}] type={kind!r} chars={len(text)} starts={text[:120]!r}")
        if kind == "text":
            try:
                json.loads(text)
                print("    parses as JSON: yes")
            except json.JSONDecodeError as error:
                print(f"    parses as JSON: no (line {error.lineno}, column {error.colno})")


def main() -> None:
    print("date (UTC):", datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
    print("cohere SDK:", importlib.metadata.version("cohere"))
    print("model:", MODEL)
    variant = sys.argv[1] if len(sys.argv) > 1 else "reduced"
    if variant not in ("reduced", "full", "full-ask-json"):
        sys.exit("usage: python repro_thinking_json.py [reduced|full|full-ask-json]")
    schema = REDUCED_SCHEMA if variant == "reduced" else full_schema()
    print("variant:", variant, f"(schema {len(json.dumps(schema))} characters)")
    client = cohere.ClientV2(api_key=os.environ["CO_API_KEY"])
    system = fetch(PROMPT_URL)
    if variant == "full-ask-json":
        system = system.rstrip("\n") + "\n\n" + ASK_JSON + "\n"
    user = "<artifact>\n" + fetch(ARTIFACT_URL) + "\n</artifact>"
    for thinking in ("disabled", "enabled"):
        response = client.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object", "json_schema": schema},
            thinking={"type": thinking},
        )
        describe(f"thinking {thinking}", response)


if __name__ == "__main__":
    main()
