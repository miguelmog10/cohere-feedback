# Command A+ with thinking off: prose before the JSON in JSON mode

Observations from building [Knowledge Automata](https://github.com/miguelmog10/knowledge-automata) (Apache 2.0), an open-source multi-agent system on Cohere's Command, Embed and Rerank. Every model reply is parsed strictly as JSON and validated by code, which is how this showed up. Observations only: we can see where the reasoning lands, not what the model does inside.

**Short version:** our system prompt was missing the JSON instruction that Cohere's docs ask for, and adding one line fixed it. What's left is a docs question (the failure we got is not the one the docs warn about), plus a few observations.

## Environment

- Model `command-a-plus-05-2026`, Cohere Python SDK 7.3.0, `ClientV2.chat`, `temperature` 0.
- `response_format={"type": "json_object", "json_schema": ...}`; `thinking={"type": "disabled"}` or `"enabled"`.
- Windows, Python 3.13, a trial API key.
- Runs on 2026-10-31 and 2026-11-02 (UTC).
- Note: on Python 3.15, installing `cohere` failed (2026-11-01) because PyYAML, which it pulls in through `tokenizers` → `huggingface-hub`, had no wheel for 3.15 yet.

## Reproduce

Needs Python 3.13 or later and a Cohere API key in the `CO_API_KEY` environment variable (or in a local `.env` file, which `.gitignore` keeps out of the repo).

With [uv](https://docs.astral.sh/uv/), which installs the exact versions pinned in `uv.lock`:

```
uv sync
uv run python repro_thinking_json.py full            # full schema, no JSON instruction
uv run python repro_thinking_json.py full-ask-json   # same, plus one system prompt line asking for JSON
uv run python repro_thinking_json.py reduced         # smaller schema, no JSON instruction
uv run python inspect_headers.py stream              # one small call: headers and IDs, streaming
```

Add `--env-file .env` after `uv run` to read the key from a `.env` file. Without uv: `pip install cohere==7.3.0`, then `python repro_thinking_json.py full`, and so on.

Each run of `repro_thinking_json.py` makes two chat calls (thinking disabled, then enabled) and prints the content blocks, `finish_reason`, usage, and whether the text block parses as JSON. Inputs are the public Decision Registrar system prompt and a fictional meeting note, read from one pinned commit of the Knowledge Automata repo. The script never prints the key or the full reply.

## The two schemas

The schema goes in the request as a JSON object, in `response_format.json_schema`. It is the contract for the answer's shape: which fields exist, their types, which are required, and what each should contain. Knowledge Automata's code validates every reply against the same schema afterwards.

**Full schema** (what Knowledge Automata sends, 2,062 characters; trimmed here). Eight decision fields, each with a description that reads like a small instruction, plus an evidence list:

```json
"content": {
  "title": "Decision log entry",
  "description": "One decision the group actually made, including a decision to reject an option. ...",
  "type": "object",
  "properties": {
    "title":     {"type": "string", "description": "Short label for the decision, about ten words or fewer."},
    "statement": {"type": "string", "description": "What was decided, as one plain sentence. ..."},
    "context": {...}, "rationale": {...}, "alternatives": {...},
    "decided_by": {...}, "decided_on": {"type": "string", "format": "date", ...}, "impacts": {...}
  },
  "required": ["title", "statement"],
  "additionalProperties": false
},
"evidence": {
  "type": "array", "items": {"type": "string"},
  "description": "Quotes copied word for word from the artifact that support the content. ..."
}
```

**Reduced schema** (a test version): four fields, no descriptions.

```json
"content": {
  "type": "object",
  "properties": {
    "title": {"type": "string"}, "statement": {"type": "string"},
    "context": {"type": "string"}, "rationale": {"type": "string"}
  },
  "required": ["title", "statement"]
},
"evidence": {"type": "array", "items": {"type": "string"}}
```

## Results

| Variant | Thinking disabled | Thinking enabled |
|---|---|---|
| Full schema, no JSON instruction | 1 text block: prose reasoning, then JSON. `finish_reason` COMPLETE, `json.loads` fails at line 1, column 1. 1,265 output tokens | thinking block + JSON-only text block, valid. 1,421 output tokens (1,189 reasoning) |
| Full schema + "Reply with one JSON object that matches the response schema, and nothing else." at the end of the system prompt | valid JSON, 3 of 3, 272 output tokens each | valid, 3 of 3. 1,165 to 1,756 output tokens (975 to 1,514 reasoning) |
| Reduced schema, no JSON instruction | valid JSON, 187 output tokens | valid. 2,214 output tokens (1,996 reasoning) |

Only one combination failed: thinking disabled, full schema, no JSON instruction. Earlier data, same system prompt and note: on 2026-10-31 that combination failed 2 of 2 (1,130 and 1,332 output tokens), and thinking enabled passed 2 of 2. In Knowledge Automata's real run, 5 of 6 first attempts failed this way, in two agents with different prompts and schemas.

## What we think this shows

- The [structured outputs page](https://docs.cohere.com/v2/docs/structured-outputs) says JSON mode output "is guaranteed to be a valid JSON object". It also asks, in an Important box, that the message explicitly instruct the model to generate JSON, warning that otherwise the model may produce an endless stream until it runs out of context. Our system prompt did not ask for JSON, so we did not meet that condition.
- The failure we got is a different one: a normal, COMPLETE reply whose text starts with the model's reasoning.
- Whether it shows up depends on the system prompt and the schema together: the reduced schema was clean without the instruction. We don't know which part of the full schema triggers it: the descriptions (which read like instructions), the extra fields, `additionalProperties: false` or `format: date`.
- The page does not mention reasoning models or the `thinking` setting.

### Evidence for question 1: did the reasoning stop, or move into the answer?

When thinking is turned off, there are two possibilities: the model really stops reasoning and just answers, or it keeps reasoning and the setting only changes where that reasoning appears.

What we saw fits the second. The failing reply (thinking disabled) begins:

```
We need to draft a decision record. Identify the most significant decision. The artifact includes a decision: "the platf…
```

and the thinking block of the same request with thinking enabled begins with the same words:

```
We need to draft a decision record. Identify the most significant decision. The artifact includes a decision: "the platf…
```

(both from the run of 2026-11-02 03:22 UTC; the full schema, no JSON instruction). So it looks as if the reasoning did not go away; it moved into the visible answer. We cannot see inside the model, so only Cohere can say which it is.

### Evidence for question 2: is the schema enforced from the first token?

With strict enforcement, the server lets the model pick only tokens that keep the answer valid against the schema, so the first token would have to be `{` and prose would be impossible. The failing reply started with prose, so with thinking disabled the enforcement seems to start later, or to be less strict than that. The fact that one system prompt line changes the outcome points the same way: with enforcement from the first token, the line would not matter. With thinking enabled, enforcement may apply only to the text block, after the thinking block. This is our reading of the observations, not something we can confirm.

## Workaround

Ask for JSON explicitly in the system prompt, whatever the thinking setting. Thinking enabled also avoided the problem without the instruction, but that is observed, not documented, and costs about 1,000 to 2,000 reasoning tokens per call here. We tested the instruction only as the last line of the system prompt (the docs example puts it in the user message).

## Also observed

- **Reasoning length varies on identical requests.** At `temperature` 0, thinking enabled, the same request used 975, 1,147 and 1,514 reasoning tokens; the thinking-disabled reply was the same each time (272 tokens). In Knowledge Automata, two identical calls of another agent billed 2,882 and 3,383 output tokens.
- **Timeouts leave nothing to report.** Two calls in Knowledge Automata hit the client timeout (60 s, then 180 s); the identical request then completed in about 18 s. The SDK does not retry a client timeout, and with a non-streaming call there is no response, no `id` and no headers to give support. Cohere's status page showed no incident.
- **Streaming gives IDs early.** With `chat_stream` (one small call, `inspect_headers.py stream`), the response headers arrived after 0.30 s, including `x-debug-trace-id`, and the message ID came with the first event, long before any timeout. Non-streaming, they arrive only with the full reply.
- **Undocumented fields.** `usage.tokens.reasoning_tokens` is returned but not listed in the Chat API reference's `usage`. `x-debug-trace-id` and `x-envoy-upstream-service-time` are sent but not documented.
- **Billed input.** Billed input tokens were 553 for both the reduced and full schemas (raw input 692 and 1,026). We assume the schema is not billed as input, but did not find this documented.

## Questions

1. With thinking off, does Command A+ still reason, only into the answer? See [the evidence for question 1](#evidence-for-question-1-did-the-reasoning-stop-or-move-into-the-answer). Related: which models does the `thinking` setting apply to? The reasoning guide names only `command-a-reasoning-08-2025`.
2. Is the schema enforced from the first token when thinking is off? See [the evidence for question 2](#evidence-for-question-2-is-the-schema-enforced-from-the-first-token).
3. Would a note for reasoning models on the structured outputs page help? Happy to open a docs PR.

### Further questions

4. Is the explicit JSON instruction required even with a schema? Which parts of a schema can make the reasoning appear in the answer (descriptions, number of fields)?
5. Can a small `token_budget` keep the JSON clean more cheaply than full thinking? When the budget runs out, can reasoning ever reach the text block?
6. For support, which ID should a client keep: the response `id` or `x-debug-trace-id`? Is `x-debug-trace-id` stable to rely on?
7. Is reasoning length expected to vary between identical requests at `temperature` 0? Does `seed` affect reasoning length?
8. What timeout do you recommend for Command A+ with thinking enabled, and is streaming the recommended way to tell "still reasoning" from "stuck"?

## Files

- `repro_thinking_json.py`: the reproduction (three variants).
- `inspect_headers.py`: one small call that prints the response headers and IDs, normal or streaming.
- `pyproject.toml`, `uv.lock`, `.python-version`: the environment, for uv.

## License

Apache 2.0, see [LICENSE](LICENSE). The investigation and write-up were done with Claude (Anthropic) as an AI pair.
