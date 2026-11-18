#!/usr/bin/env python3
"""A stand-in for `claude -p --input-format stream-json ...` used by the tests.

It answers every message with a canned reply, streamed the way Claude Code
streams, so the server can be tested without a Claude login.
"""
import json
import sys
import uuid

args = sys.argv[1:]
session = args[args.index("--resume") + 1] if "--resume" in args else str(uuid.uuid4())


def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


if "-p" in args and "--input-format" not in args:      # a background build
    out({"type": "system", "subtype": "init", "session_id": session})
    out({"type": "assistant", "message": {"id": "b1", "content": [{"type": "text", "text": "Building."}]}})
    out({"type": "result", "subtype": "success", "is_error": False, "result": "done",
         "session_id": session, "total_cost_usd": 0.12})
    sys.exit(0)

out({"type": "system", "subtype": "init", "session_id": session})
for line in sys.stdin:
    msg = json.loads(line)
    text = msg["message"]["content"]
    mid = "msg_" + uuid.uuid4().hex[:6]
    if "dutch" in text.lower() or text.startswith("[nl]"):
        reply = "Goed, meneer. Ik heb het genoteerd. Is er nog iets dat ik voor u kan doen?"
    else:
        reply = f"Certainly, sir. You said: {text[5:]}. Anything else I can do for you?"
    out({"type": "stream_event", "event": {"type": "message_start", "message": {"id": mid}}})
    out({"type": "stream_event", "event": {"type": "content_block_start", "index": 0}})
    for i in range(0, len(reply), 7):
        out({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": reply[i:i + 7]}}})
    out({"type": "stream_event", "event": {"type": "content_block_stop", "index": 0}})
    out({"type": "assistant", "message": {"id": mid, "content": [
        {"type": "text", "text": reply},
        {"type": "tool_use", "name": "mcp__jarvis__system_status", "input": {}}]}})
    out({"type": "result", "subtype": "success", "is_error": False, "result": reply,
         "session_id": session, "total_cost_usd": 0.01})
