"""Arm F: one persistent Gemini Live session driven by collector JSONL.

The optional google-genai dependency is imported only when a real session is
started.  stdout is exclusively bounded JSONL; diagnostics never include API
keys.  Query evidence and realtime media are restricted to captures at or
before the collector's query_ms watermark.
"""
import argparse
import asyncio
import base64
import json
import math
import os
import struct
import sys
import time

from gamst_bench.contracts import canonical, require


def _field(value, name, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _default_session_factory():
    try:
        from google import genai
    except ImportError as exc:
        raise ImportError(
            "Gemini Live requires the optional google-genai package; "
            "install it with 'python -m pip install google-genai'"
        ) from exc
    api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    require(api_key, 'set GOOGLE_API_KEY or GEMINI_API_KEY for Gemini Live')
    client = genai.Client(api_key=api_key)

    def factory(*, model, config):
        return client.aio.live.connect(model=model, config=config)

    return factory


def _pcm16le(payload):
    """Return little-endian PCM16, accepting benchmark float PCM or PCM16."""
    if payload.get('pcm_s16_base64') is not None:
        raw = base64.b64decode(payload['pcm_s16_base64'], validate=True)
        require(len(raw) % 2 == 0, 'PCM16 input must contain complete samples')
        return raw
    raw = base64.b64decode(payload['pcm_f32_base64'], validate=True)
    require(len(raw) % 4 == 0, 'float PCM input must contain complete samples')
    samples = []
    for (sample,) in struct.iter_unpack('<f', raw):
        require(math.isfinite(sample), 'float PCM samples must be finite')
        sample = max(-1.0, min(1.0, sample))
        samples.append(int(round(sample * 32767)))
    return struct.pack('<' + 'h' * len(samples), *samples)


def _native_answer(raw, allowed_evidence):
    """Read native JSON when supplied, otherwise preserve the native text."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return raw, []
    if not isinstance(value, dict) or not isinstance(value.get('answer'), str):
        return raw, []
    references = value.get('evidence_ids', [])
    if not isinstance(references, list):
        references = []
    # Model citations are claims, not authority: drop unknown and post-cutoff IDs.
    references = [ref for ref in references
                  if isinstance(ref, str) and ref in allowed_evidence]
    return value['answer'], list(dict.fromkeys(references))


class Adapter:
    def __init__(self, args, session_factory=None):
        self.args = args
        self.session_factory = session_factory
        self.model = getattr(args, 'model', None)
        self.session = None
        self.session_context = None
        self.receiver = None
        self.started = False
        self.ended = False
        self.answered = False
        self.query_sent = False
        self.query_cutoff = None
        self.known = {}
        self.sent = set()
        self.last_video_at = None
        self.response_parts = []
        self.usage = {}
        self.receiver_error = None
        self.answer_ready = asyncio.Event()
        self.closing = False
        self.capture_origin_ms = None

    def emit(self, kind, **values):
        sys.stdout.buffer.write(canonical({'type': kind, **values}) + b'\n')
        sys.stdout.buffer.flush()

    def emit_error(self, exc):
        # SDK exceptions can echo request details. Type names are sufficient for
        # unexpected failures; actionable local configuration errors are safe.
        if isinstance(exc, (ImportError, ValueError)):
            text = str(exc)
            for name in ('GOOGLE_API_KEY', 'GEMINI_API_KEY'):
                secret = os.environ.get(name)
                if secret:
                    text = text.replace(secret, '[REDACTED]')
        else:
            text = type(exc).__name__
        self.emit('error', text=text[:4096], failure_category=type(exc).__name__)

    async def start(self, message):
        require(not self.started, 'duplicate start')
        configuration = message['configuration']
        self.model = self.model or configuration.get('model')
        require(isinstance(self.model, str) and self.model,
                'Gemini Live model required via configuration.model or --model')
        self.capture_origin_ms = int(time.time() * 1000)
        factory = self.session_factory or _default_session_factory()
        self.session_context = factory(
            model=self.model, config={'response_modalities': ['TEXT']})
        self.session = await self.session_context.__aenter__()
        self.started = True
        self.receiver = asyncio.create_task(self._receive())
        self.emit('meta', provider='google_genai_live', model=self.model,
                  lifecycle='ready', persistent_sessions=1, video_fps=1,
                  audio_encoding='pcm_s16le', audio_sample_rate=16000,
                  audio_channels=1, query_cutoff_enforced=True,
                  evidence_class=getattr(self.args, 'evidence_class', 'smoke'),
                  capture_origin_ms=self.capture_origin_ms,
                  accounting='Native Gemini Live usage metadata only; device and network costs are excluded.')

    async def input(self, item):
        require(self.started and not self.ended, 'input outside active session')
        input_id = item['id']
        require(isinstance(input_id, str) and input_id not in self.known,
                'input IDs must be unique strings')
        at_ms = item.get('at_ms')
        require(type(at_ms) is int and at_ms >= 0,
                'input at_ms must be a nonnegative integer')
        self.known[input_id] = item
        if self.query_cutoff is not None and at_ms > self.query_cutoff:
            return
        if self.answered:
            return
        modality = item.get('modality')
        payload = item.get('payload', {})
        if modality == 'control':
            return
        if modality == 'video':
            # Use capture time, not processing time, for causal 1 FPS sampling.
            if self.last_video_at is not None and at_ms < self.last_video_at + 1000:
                return
            jpeg = base64.b64decode(payload['jpeg_base64'], validate=True)
            await self.session.send_realtime_input(
                video={'data': jpeg, 'mime_type': 'image/jpeg'})
            self.last_video_at = at_ms
        elif modality == 'audio':
            sample_rate = payload.get('sample_rate', 16000)
            require(type(sample_rate) is int and sample_rate > 0,
                    'audio sample_rate must be a positive integer')
            require(payload.get('channels', 1) == 1,
                    'Gemini Live adapter requires mono audio')
            pcm = _pcm16le(payload)
            await self.session.send_realtime_input(audio={
                'data': pcm, 'mime_type': 'audio/pcm;rate=' + str(sample_rate)})
        elif modality == 'text':
            await self.session.send_realtime_input(text=payload['text'])
        elif modality == 'signal':
            await self.session.send_realtime_input(text=json.dumps(payload, ensure_ascii=False))
        else:
            raise ValueError('unsupported Gemini Live input modality: ' + str(modality))
        self.sent.add(input_id)

    async def query(self, message):
        require(self.started and not self.ended, 'query outside active session')
        require(not self.query_sent, 'duplicate query')
        query = message.get('query')
        require(isinstance(query, str), 'query must be a string')
        cutoff = message.get('query_ms')
        require(type(cutoff) is int and cutoff >= 0,
                'query_ms must be a nonnegative integer')
        self.query_cutoff = cutoff
        eligible = {input_id: item['at_ms']
                    for input_id, item in self.known.items()
                    if input_id in self.sent and item['at_ms'] <= cutoff}
        prompt = json.dumps({
            'question': query,
            'query_cutoff_ms': cutoff,
            'eligible_evidence': eligible,
            'instructions': (
                'Use only realtime inputs captured at or before query_cutoff_ms. '
                'Never use or cite later inputs. Return only JSON with string '
                'answer and evidence_ids array; evidence_ids must be drawn from '
                'eligible_evidence. Distinguish unknown, current, and last-seen.'
            ),
        }, ensure_ascii=False)
        self.query_sent = True
        await self.session.send_client_content(
            turns={'role': 'user', 'parts': [{'text': prompt}]}, turn_complete=True)
        # Keep the collector from ending the task before the native final turn.
        await self.answer_ready.wait()
        if self.receiver_error is not None:
            raise self.receiver_error

    def _record_usage(self, response):
        metadata = _field(response, 'usage_metadata')
        if metadata is None:
            return
        for name in ('prompt_token_count', 'candidates_token_count',
                     'total_token_count', 'cached_content_token_count'):
            value = _field(metadata, name)
            if type(value) is int and value >= 0:
                self.usage[name] = value

    def _handle_response(self, response):
        self._record_usage(response)
        text = _field(response, 'text')
        if not text:
            server_content = _field(response, 'server_content')
            model_turn = _field(server_content, 'model_turn')
            parts = _field(model_turn, 'parts', ()) or ()
            text = ''.join(_field(part, 'text', '') or '' for part in parts)
        if text:
            self.response_parts.append(text)
        complete = bool(_field(_field(response, 'server_content'), 'turn_complete', False))
        if not complete:
            return
        raw = ''.join(self.response_parts).strip()
        self.response_parts.clear()
        if not self.query_sent or self.answered:
            return
        require(raw, 'Gemini Live final response contained no text')
        eligible = {input_id for input_id, item in self.known.items()
                    if input_id in self.sent and item['at_ms'] <= self.query_cutoff}
        answer, references = _native_answer(raw, eligible)
        require(len(answer) <= 32768, 'Gemini Live answer exceeds collector bound')
        self.answered = True
        self.emit('answer', text=answer, evidence_ids=references)
        self.answer_ready.set()

    async def _receive(self):
        try:
            while not self.closing and not self.answered:
                async for response in self.session.receive():
                    self._handle_response(response)
                    if self.answered:
                        return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.receiver_error = exc
            self.emit_error(exc)
            self.answer_ready.set()

    async def finish(self):
        if self.ended:
            return
        self.ended = True
        self.closing = True
        if self.receiver is not None:
            self.receiver.cancel()
            await asyncio.gather(self.receiver, return_exceptions=True)
        if self.session_context is not None and self.started:
            await self.session_context.__aexit__(None, None, None)
        if self.started:
            self.emit('usage', calls=int(self.query_sent),
                      cost_quantities=dict(self.usage) if self.usage else None)
            self.emit('meta', provider='google_genai_live', lifecycle='stopped',
                      persistent_sessions=1, ready=False)
        self.started = False


async def run(args, session_factory=None):
    adapter = Adapter(args, session_factory=session_factory)
    try:
        max_line = 6 * 1024 * 1024
        while line := await asyncio.to_thread(sys.stdin.buffer.readline, max_line + 1):
            require(len(line) <= max_line and line.endswith(b'\n'),
                    'bounded newline required')
            message = json.loads(line)
            kind = message.get('type') if isinstance(message, dict) else None
            if kind == 'start':
                await adapter.start(message)
            elif kind == 'input':
                await adapter.input(message['input'])
            elif kind == 'query':
                await adapter.query(message)
            elif kind == 'end':
                await adapter.finish()
                return
            else:
                raise ValueError('unsupported adapter message')
        if adapter.started and not adapter.ended:
            raise ValueError('adapter input ended before end')
    except Exception as exc:
        if adapter.receiver_error is not exc:
            adapter.emit_error(exc)
        await adapter.finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default=None,
                        help='Gemini Live model; defaults to configuration.model')
    parser.add_argument('--evidence-class', choices=('smoke', 'measured', 'synthetic'),
                        default='smoke')
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
