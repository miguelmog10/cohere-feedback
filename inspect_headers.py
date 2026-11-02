"""One small Command A+ call that prints the HTTP response headers and the timing.

Looks for a request ID a client could keep even if it later gives up on a call.
Needs only the Cohere SDK and an API key: pip install cohere; set CO_API_KEY.
Prints header names, and values only for headers that look like IDs or timing;
never prints the key. One chat call.

    python inspect_headers.py          # normal chat: headers arrive with the reply
    python inspect_headers.py stream   # streaming: when do headers and the first
                                       # thinking and text deltas arrive?
"""

import importlib.metadata
import os
import sys
import time

import cohere

MODEL = "command-a-plus-05-2026"
SHOW_VALUES = ("id", "trace", "request", "version", "date", "server-timing", "x-envoy")
REQUEST = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "Reply with the word ready."}],
    "temperature": 0,
    "thinking": {"type": "enabled"},
}


def print_headers(headers: dict) -> None:
    print("headers:")
    for name, value in sorted(headers.items()):
        shown = value if any(key in name.lower() for key in SHOW_VALUES) else "(value hidden)"
        print(f"  {name}: {shown}")


def plain(client: cohere.ClientV2) -> None:
    started = time.perf_counter()
    raw = client.with_raw_response.chat(**REQUEST)
    print(f"status: {raw.status_code}  elapsed: {time.perf_counter() - started:.2f} s")
    print("response body id:", raw.data.id)
    print("usage:", raw.data.usage)
    print_headers(raw.headers)


def stream(client: cohere.ClientV2) -> None:
    started = time.perf_counter()
    with client.with_raw_response.chat_stream(**REQUEST) as raw:
        print(f"status: {raw.status_code}  headers after: {time.perf_counter() - started:.2f} s")
        print_headers(raw.headers)
        first: dict[str, float] = {}
        for event in raw.data:
            kind = getattr(event, "type", None)
            if kind == "message-start":
                print("message-start id:", getattr(event, "id", None))
            content = getattr(getattr(getattr(event, "delta", None), "message", None), "content", None)
            for part in ("thinking", "text"):
                if getattr(content, part, None) and part not in first:
                    first[part] = time.perf_counter() - started
            if kind == "message-end":
                usage = getattr(getattr(event, "delta", None), "usage", None)
                print("usage:", usage)
        for part, seconds in first.items():
            print(f"first {part} delta after: {seconds:.2f} s")
        print(f"stream ended after: {time.perf_counter() - started:.2f} s")


def main() -> None:
    print("cohere SDK:", importlib.metadata.version("cohere"))
    client = cohere.ClientV2(api_key=os.environ["CO_API_KEY"])
    mode = sys.argv[1] if len(sys.argv) > 1 else "plain"
    if mode not in ("plain", "stream"):
        sys.exit("usage: python inspect_headers.py [plain|stream]")
    if mode == "plain":
        plain(client)
    else:
        stream(client)


if __name__ == "__main__":
    main()
