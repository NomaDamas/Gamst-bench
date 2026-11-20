"""Model clients shared by every benchmark.

- ask_local: Qwen3.5-9B (vLLM :8000), thinking off — arm B and C-local consumer.
- ask_gemini: gemini-3.8-flash on Vertex AI (global) — C-Gemini consumer. Never Gemini 3.1 Pro.
- jev_create_watch: Qwen3.8-27B-FP8 (vLLM :8001) turns a user sentence into MCP create_watch
  arguments using the tool schema GAMST publishes. Up to 2 attempts; a schema error from GAMST is
  fed back once. jev never edits a Watch silently.

Every call returns (text, usage, latency_s); usage is the provider's token accounting.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

LOCAL = os.environ.get("PAR_LOCAL", "http://127.0.0.1:8000/v1")
JEV = os.environ.get("PAR_JEV", "http://127.0.0.1:8001/v1")
GEMINI = os.environ.get("PAR_GEMINI", "gemini-3.8-flash")
PROJECT = "optimum-zone"
assert "3.1-pro" not in GEMINI, "Gemini 3.1 Pro is not allowed in this experiment"


def _post(url, body, headers=None, timeout=300):
    request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _content(user_text, frames):
    content = []
    for t, b64 in frames:
        content.append({"type": "text", "text": f"[t={t}s]"})
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}})
    content.append({"type": "text", "text": user_text})
    return content


def ask_local(system, user_text, frames, max_tokens=128):
    started = time.time()
    data = _post(LOCAL + "/chat/completions", {
        "model": "qwen3.5-9b", "temperature": 0, "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": _content(user_text, frames)}]})
    return (data["choices"][0]["message"].get("content") or "").strip(), data.get("usage"), time.time() - started


_token = {"value": None, "expires": 0}


def _gcp_token():
    if time.time() < _token["expires"] - 60:
        return _token["value"]
    request = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read())
    _token.update(value=data["access_token"], expires=time.time() + data["expires_in"])
    return _token["value"]


def ask_gemini(system, user_text, frames, max_tokens=128):
    parts = []
    for t, b64 in frames:
        parts += [{"text": f"[t={t}s]"}, {"inlineData": {"mimeType": "image/jpeg", "data": b64}}]
    parts.append({"text": user_text})
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens,
                                 "thinkingConfig": {"thinkingLevel": "low"}}}
    url = (f"https://aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/global/publishers/google/"
           f"models/{GEMINI}:generateContent")
    started = time.time()
    for attempt in range(4):
        try:
            data = _post(url, body, {"Authorization": "Bearer " + _gcp_token(), "x-goog-user-project": PROJECT})
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 503) or attempt == 3:
                raise
            time.sleep(2 ** attempt * 3)
    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"].get("parts", []) if not p.get("thought"))
    meta = data.get("usageMetadata", {})
    usage = {"prompt_tokens": meta.get("promptTokenCount"), "completion_tokens": meta.get("candidatesTokenCount"),
             "thoughts_tokens": meta.get("thoughtsTokenCount"), "total_tokens": meta.get("totalTokenCount")}
    return text.strip(), usage, time.time() - started


JEV_SYSTEM = ("You are jev, the application's decision model. You turn the user's request into GAMST Watches by "
              "calling the create_watch tool. GAMST evaluates the rule deterministically; you cannot see video. "
              "Use only capability_id values and value fields that exist in the capability list. owner is 'user' "
              "because the user asked. Choose cooldown_ms and max_per_minute from the user's words. Call the tool "
              "exactly once.")


def jev_create_watch(request, tools, capabilities, hint=None, validate=None):
    """Return (create_watch arguments or None, log). ``validate(args)`` may raise to request one retry."""
    openai_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                      "parameters": t["inputSchema"]}} for t in tools]
    listing = json.dumps(capabilities, ensure_ascii=False)[:12000]
    user = f"Capabilities (from list_capabilities): {listing}\n"
    if hint:
        user += f"Rule-specific capability prepared for this request: {json.dumps(hint)}\n"
    user += f"User request: {request}"
    messages = [{"role": "system", "content": JEV_SYSTEM}, {"role": "user", "content": user}]
    log = []
    for attempt in range(2):
        started = time.time()
        data = _post(JEV + "/chat/completions", {"model": "jev", "temperature": 0, "max_tokens": 1024,
                                                  "chat_template_kwargs": {"enable_thinking": False},
                                                  "tools": openai_tools, "tool_choice": "required",
                                                  "messages": messages})
        message = data["choices"][0]["message"]
        call = (message.get("tool_calls") or [None])[0]
        entry = {"attempt": attempt, "latency_s": round(time.time() - started, 2), "usage": data.get("usage"),
                 "tool_call": call}
        log.append(entry)
        if not call:
            continue
        args = json.loads(call["function"]["arguments"])
        try:
            if validate:
                validate(args)
            return args, log
        except Exception as exc:  # GAMST rejected the rule: one corrective round
            entry["rejected"] = f"{type(exc).__name__}: {exc}"[:300]
            messages += [message, {"role": "tool", "tool_call_id": call["id"],
                                   "content": f"GAMST rejected the call: {entry['rejected']}"}]
    return None, log
