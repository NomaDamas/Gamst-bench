"""Run the pinned StreamArena judge against Vertex AI Gemini with OAuth bearer auth.

Only transport auth is replaced (Vertex rejects the native `api-key` header);
prompt, parsing and aggregation stay in the pinned `streamarena.judge` module.
The token is read from the environment and never written to disk.
"""
import os
import sys

sys.path.insert(0, sys.argv.pop(1))  # StreamArena checkout root
from streamarena import judge  # noqa: E402

_token = os.environ["VERTEX_ACCESS_TOKEN"]


def _headers(api_key, url):
    return {"content-type": "application/json", "authorization": f"Bearer {_token}"}


judge.build_judge_headers = _headers
sys.exit(judge._cli())
