import asyncio
import base64
import io
import json
import os
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gamst_bench.adapters.gamst_http import request_chat
from gamst_bench.adapters.gemini_live import Adapter as GeminiLiveAdapter


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit):
        return json.dumps({
            'choices': [{'message': {'content': 'ok'}}],
            'usage': {'prompt_tokens': 2, 'completion_tokens': 1},
        }).encode()


class FakeOpener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return FakeResponse()


class CommercialHTTPTests(unittest.TestCase):
    def call(self, endpoint, *, allow_remote=True, key_env=None):
        opener = FakeOpener()
        with patch('gamst_bench.adapters.gamst_http.urllib.request.build_opener',
                   return_value=opener):
            text, usage = request_chat(endpoint, 'model', [], allow_remote,
                                       key_env=key_env)
        self.assertEqual(text, 'ok')
        self.assertEqual(usage['prompt_tokens'], 2)
        return opener.requests[0]

    def test_remote_requires_opt_in_and_https_but_local_http_remains_available(self):
        with patch('gamst_bench.adapters.gamst_http.urllib.request.build_opener') as build:
            with self.assertRaisesRegex(ValueError, 'allow-remote'):
                request_chat('https://example.com/v1', 'model', [])
            with self.assertRaisesRegex(ValueError, 'allow-remote'):
                request_chat('http://example.com/v1', 'model', [], True)
            build.assert_not_called()
        request = self.call('http://127.0.0.1:8080/v1', allow_remote=False)
        self.assertEqual(request.full_url,
                         'http://127.0.0.1:8080/v1/chat/completions')

    def test_url_credentials_and_query_are_rejected(self):
        for endpoint in ('https://user:password@example.com/v1',
                         'https://example.com/v1?key=secret'):
            with self.assertRaisesRegex(ValueError, 'credentials'):
                request_chat(endpoint, 'model', [], True)

    def test_role_environment_names_select_role_tokens_and_legacy_fallback(self):
        environment = {
            'VLM_TOKEN': 'vlm-secret',
            'CONSUMER_TOKEN': 'consumer-secret',
            'GAMST_BENCH_API_KEY': 'legacy-secret',
        }
        with patch.dict(os.environ, environment, clear=True):
            vlm = self.call('https://example.com/v1', key_env='VLM_TOKEN')
            consumer = self.call('https://example.com/v1', key_env='CONSUMER_TOKEN')
            legacy = self.call('https://example.com/v1')
            missing_role = self.call('https://example.com/v1', key_env='MISSING_TOKEN')
        self.assertEqual(vlm.get_header('Authorization'), 'Bearer vlm-secret')
        self.assertEqual(consumer.get_header('Authorization'), 'Bearer consumer-secret')
        self.assertEqual(legacy.get_header('Authorization'), 'Bearer legacy-secret')
        self.assertIsNone(missing_role.get_header('Authorization'))

    def test_base_and_full_vertex_and_gemini_urls_are_not_double_appended(self):
        cases = [
            ('https://example.com/v1/',
             'https://example.com/v1/chat/completions'),
            ('https://generativelanguage.googleapis.com/v1beta/openai',
             'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'),
            ('https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
             'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'),
            ('https://us-central1-aiplatform.googleapis.com/v1/projects/project/locations/us-central1/endpoints/openapi/chat/completions',
             'https://us-central1-aiplatform.googleapis.com/v1/projects/project/locations/us-central1/endpoints/openapi/chat/completions'),
        ]
        for endpoint, expected in cases:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.call(endpoint).full_url, expected)


class FakeLiveSession:
    def __init__(self):
        self.realtime = []
        self.client_content = []
        self.turns = asyncio.Queue()
        self.query_received = asyncio.Event()
        self.closed = False

    async def send_realtime_input(self, **payload):
        self.realtime.append(payload)

    async def send_client_content(self, **payload):
        self.client_content.append(payload)
        self.query_received.set()

    async def receive(self):
        responses = await self.turns.get()
        for response in responses:
            yield response


class FakeLiveContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        self.session.closed = True


class GeminiLiveTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = FakeLiveSession()
        self.factory_calls = []

        def factory(*, model, config):
            self.factory_calls.append((model, config))
            return FakeLiveContext(self.session)

        self.stdout = SimpleNamespace(buffer=io.BytesIO())
        self.stdout_patch = patch.object(sys, 'stdout', self.stdout)
        self.stdout_patch.start()
        self.adapter = GeminiLiveAdapter(SimpleNamespace(model='gemini-live-test'),
                                         session_factory=factory)

    def tearDown(self):
        self.stdout_patch.stop()

    async def start(self):
        await self.adapter.start({
            'type': 'start',
            'configuration': {'policy': 'streaming'},
            'consumer_model': 'unused-consumer',
        })

    def outputs(self, kind=None):
        rows = [json.loads(line) for line in
                self.stdout.buffer.getvalue().splitlines()]
        return [row for row in rows if kind is None or row['type'] == kind]

    async def test_realtime_video_is_one_fps_and_audio_is_pcm16_mono(self):
        await self.start()
        await self.adapter.input({
            'id': 'video-0', 'at_ms': 0, 'modality': 'video',
            'payload': {'jpeg_base64': base64.b64encode(b'jpeg-zero').decode()},
        })
        await self.adapter.input({
            'id': 'video-500', 'at_ms': 500, 'modality': 'video',
            'payload': {'jpeg_base64': base64.b64encode(b'dropped').decode()},
        })
        await self.adapter.input({
            'id': 'audio', 'at_ms': 600, 'modality': 'audio',
            'payload': {
                'pcm_f32_base64': base64.b64encode(
                    struct.pack('<4f', -1.0, -0.5, 0.0, 1.0)).decode(),
                'sample_rate': 16000,
            },
        })
        await self.adapter.input({
            'id': 'video-1000', 'at_ms': 1000, 'modality': 'video',
            'payload': {'jpeg_base64': base64.b64encode(b'jpeg-one').decode()},
        })
        await self.adapter.finish()

        videos = [row['video'] for row in self.session.realtime if 'video' in row]
        self.assertEqual([row['data'] for row in videos], [b'jpeg-zero', b'jpeg-one'])
        self.assertTrue(all(row['mime_type'] == 'image/jpeg' for row in videos))
        audio = next(row['audio'] for row in self.session.realtime if 'audio' in row)
        self.assertEqual(audio['mime_type'], 'audio/pcm;rate=16000')
        self.assertEqual(struct.unpack('<4h', audio['data']),
                         (-32767, -16384, 0, 32767))
        self.assertEqual(self.factory_calls, [
            ('gemini-live-test', {'response_modalities': ['TEXT']})])
        self.assertTrue(self.session.closed)
        self.assertEqual(self.outputs('usage')[0]['calls'], 0)
        self.assertEqual(len(self.outputs('meta')), 2)

    async def test_native_answer_usage_meta_and_cutoff_evidence(self):
        await self.start()
        await self.adapter.input({
            'id': 'before', 'at_ms': 100, 'modality': 'video',
            'payload': {'jpeg_base64': base64.b64encode(b'before').decode()},
        })
        query_task = asyncio.create_task(self.adapter.query({
            'type': 'query', 'query': 'What changed?', 'query_ms': 1000,
        }))
        await self.session.query_received.wait()
        await self.adapter.input({
            'id': 'after', 'at_ms': 1001, 'modality': 'video',
            'payload': {'jpeg_base64': base64.b64encode(b'after').decode()},
        })
        self.assertEqual(len(self.session.realtime), 1)

        content = self.session.client_content[0]
        self.assertTrue(content['turn_complete'])
        prompt = json.loads(content['turns']['parts'][0]['text'])
        self.assertEqual(prompt['question'], 'What changed?')
        self.assertEqual(prompt['query_cutoff_ms'], 1000)
        self.assertEqual(prompt['eligible_evidence'], {'before': 100})

        native_answer = json.dumps({
            'answer': 'The pre-cutoff frame changed.',
            'evidence_ids': ['before', 'after', 'unknown'],
        })
        split = len(native_answer) // 2
        self.session.turns.put_nowait([
            SimpleNamespace(
                text=native_answer[:split],
                server_content=SimpleNamespace(turn_complete=False),
                usage_metadata=SimpleNamespace(prompt_token_count=20),
            ),
            SimpleNamespace(
                text=native_answer[split:],
                server_content=SimpleNamespace(turn_complete=True),
                usage_metadata=SimpleNamespace(
                    prompt_token_count=20, candidates_token_count=7,
                    total_token_count=27),
            ),
            SimpleNamespace(
                text='{"answer":"must not be emitted"}',
                server_content=SimpleNamespace(turn_complete=True),
                usage_metadata=None,
            ),
        ])
        await query_task
        await self.adapter.finish()

        answers = self.outputs('answer')
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0], {
            'type': 'answer', 'text': 'The pre-cutoff frame changed.',
            'evidence_ids': ['before'],
        })
        usage = self.outputs('usage')[0]
        self.assertEqual(usage['calls'], 1)
        self.assertEqual(usage['cost_quantities'], {
            'prompt_token_count': 20,
            'candidates_token_count': 7,
            'total_token_count': 27,
        })
        ready, stopped = self.outputs('meta')
        self.assertEqual((ready['lifecycle'], stopped['lifecycle']),
                         ('ready', 'stopped'))
        self.assertEqual(ready['persistent_sessions'], 1)
        self.assertTrue(ready['query_cutoff_enforced'])
        self.assertNotIn('GOOGLE_API_KEY', json.dumps(ready))


if __name__ == '__main__':
    unittest.main()
