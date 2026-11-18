"""Run the pinned StreamArena judge against Vertex AI Gemini with OAuth bearer auth.

Two transport-level substitutions, both documented in the campaign report:
- Vertex rejects the native `api-key` header, so auth is an OAuth bearer token
  read from VERTEX_ACCESS_TOKEN (never written to disk).
- Gemini 3.x Pro on Vertex counts thinking tokens against maxOutputTokens; the
  native budget of 10 then yields no answer part ("<err ...: 'content'>"). The
  wrapper sets thinkingLevel LOW and adds thinking headroom on top of the native
  10 answer tokens. Prompt, parsing and aggregation stay in `streamarena.judge`.
"""
import json
import os
import sys

sys.path.insert(0, sys.argv.pop(1))  # StreamArena checkout root
from streamarena import judge  # noqa: E402

_token = os.environ["VERTEX_ACCESS_TOKEN"]
_post = judge.requests.post
THINKING_HEADROOM = 2048


def _headers(api_key, url):
    return {"content-type": "application/json", "authorization": f"Bearer {_token}"}


def _post_with_headroom(url, data=None, **kwargs):
    payload = json.loads(data)
    config = payload.setdefault("generationConfig", {})
    config["maxOutputTokens"] = config.get("maxOutputTokens", 10) + THINKING_HEADROOM
    config["thinkingConfig"] = {"thinkingLevel": "LOW"}
    return _post(url, data=json.dumps(payload), **kwargs)


judge.build_judge_headers = _headers
judge.requests.post = _post_with_headroom
sys.exit(judge._cli())
