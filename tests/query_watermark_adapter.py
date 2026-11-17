"""Protocol test adapter that echoes the collector's internal query watermark."""
import json
import sys

refs = []
for line in sys.stdin:
    message = json.loads(line)
    if message["type"] == "input":
        refs.append(message["input"]["id"])
    elif message["type"] == "query":
        print(json.dumps({"type": "meta", "query_ms": message.get("query_ms")}), flush=True)
        print(json.dumps({"type": "answer", "text": "watermark received",
                          "evidence_ids": refs[-1:]}), flush=True)
    elif message["type"] == "end":
        break
