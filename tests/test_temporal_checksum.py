import copy
import hashlib
import asyncio
import json
import sys
import textwrap
import unittest

from gamst_bench.contracts import (
    PacketIntegrityCounter,
    canonical_packet_bytes,
    packet_checksum,
    packet_sha256,
    verify_packet_checksum,
)


class TemporalChecksumTests(unittest.TestCase):
    def test_canonical_bytes_match_cross_runtime_contract(self):
        packet = {
            "z": "마지막",
            "schema_version": "gamst.temporal.v1",
            "events": [],
            "checksum": {"algorithm": "sha256", "version": 1, "sha256": "ignored"},
            "clock": {"source": "camera"},
        }
        expected = b'{"clock":{"source":"camera"},"events":[],"schema_version":"gamst.temporal.v1","z":"\xeb\xa7\x88\xec\xa7\x80\xeb\xa7\x89"}'
        self.assertEqual(canonical_packet_bytes(packet), expected)
        self.assertEqual(packet_sha256(packet), hashlib.sha256(expected).hexdigest())

    def test_checksum_round_trip_and_tamper_is_counted(self):
        packet = {"schema_version": "gamst.temporal.v1", "events": [], "query_cutoff_ms": 4}
        packet["checksum"] = packet_checksum(packet)
        counter = PacketIntegrityCounter()
        self.assertTrue(verify_packet_checksum(packet, counter=counter))
        self.assertEqual(counter.integrity_rejected, 0)
        tampered = copy.deepcopy(packet)
        tampered["query_cutoff_ms"] = 5
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            verify_packet_checksum(tampered, counter=counter)
        self.assertEqual(counter.integrity_rejected, 1)

    def test_unsupported_version_and_legacy_are_explicit(self):
        packet = {"schema_version": "gamst.temporal.v1", "events": []}
        counter = PacketIntegrityCounter()
        legacy = verify_packet_checksum(packet, counter=counter, allow_legacy=True)
        self.assertFalse(legacy)
        self.assertEqual(counter.integrity_rejected, 0)
        packet["checksum"] = {"algorithm": "sha256", "version": 2, "sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "unsupported"):
            verify_packet_checksum(packet, counter=counter)
        self.assertEqual(counter.integrity_rejected, 1)

    def test_counter_is_bounded(self):
        counter = PacketIntegrityCounter(limit=1)
        packet = {"schema_version": "gamst.temporal.v1"}
        for _ in range(3):
            with self.assertRaises(ValueError):
                verify_packet_checksum(packet, counter=counter)
        self.assertEqual(counter.integrity_rejected, 1)

    def test_collector_rejects_tampered_embedded_packet_before_dispatch(self):
        from gamst_bench.collect import run_task
        from gamst_bench.fixtures import make_fixture

        plan, _, _, _ = make_fixture()
        task = copy.deepcopy(plan["tasks"][0])
        task.update(duration_ms=100, query_ms=50, available_ms=0, deadline_ms=100)
        task["inputs"] = task["inputs"][:1]
        from gamst_bench.contracts import freeze
        plan["tasks"] = [task]
        plan["timeout_ms"] = 1000
        plan = freeze(plan)
        body = {"schema_version": "gamst.temporal.v1", "events": [], "query_cutoff_ms": 0}
        body["checksum"] = packet_checksum(body)
        body["query_cutoff_ms"] = 1  # tamper after signing
        script = (
            "import json,sys; p=json.loads(sys.argv[1]); "
            "[print(json.dumps({'type':'context','text':'x','evidence_ids':[json.loads(x)['input']['id']], 'packet':p}),flush=True) "
            "for x in sys.stdin if json.loads(x)['type']=='input']"
        )

        async def exercise():
            return await run_task(plan, plan["systems"][0], task,
                                  [sys.executable, "-u", "-c", script, json.dumps(body)])

        trace = asyncio.run(exercise())
        self.assertEqual(trace["status"], "error")
        self.assertEqual(trace["integrity_rejected"], 1)
        self.assertEqual(trace["outputs"], [])

    def test_trace_retains_measured_provenance_and_packet_checksum(self):
        from gamst_bench.collect import run_task
        from gamst_bench.fixtures import make_fixture
        from gamst_bench.contracts import freeze

        plan, _, _, _ = make_fixture()
        task = copy.deepcopy(plan["tasks"][0])
        task.update(duration_ms=100, query_ms=50, available_ms=0, deadline_ms=100)
        task["inputs"] = task["inputs"][:1]
        plan["tasks"] = [task]
        plan["timeout_ms"] = 1000
        plan = freeze(plan)
        commits = {
            "gamst": "a" * 40,
            "gamstcrew": "b" * 40,
            "gamst-bench": "c" * 40,
        }
        packet = {"schema_version": "gamst.temporal.v1", "events": [], "query_cutoff_ms": 0}
        packet["checksum"] = packet_checksum(packet)
        script = textwrap.dedent(
            """
            import json, sys
            p = json.loads(sys.argv[1])
            for line in sys.stdin:
                x = json.loads(line)
                if x['type'] == 'start':
                    print(json.dumps({'type': 'meta', 'text': json.dumps(x.get('provenance', {}), sort_keys=True)}), flush=True)
                elif x['type'] == 'input':
                    print(json.dumps({'type': 'context', 'text': 'x', 'evidence_ids': [x['input']['id']], 'packet': p}), flush=True)
                elif x['type'] == 'query':
                    print(json.dumps({'type': 'answer', 'text': 'ok', 'evidence_ids': []}), flush=True)
                elif x['type'] == 'end':
                    break
            """
        )

        async def exercise():
            return await run_task(
                plan, plan["systems"][0], task,
                [sys.executable, "-u", "-c", script, json.dumps(packet)],
                runtime_manifest_sha256="d" * 64,
                repository_commits=commits,
            )

        trace = asyncio.run(exercise())
        self.assertEqual(trace["status"], "success")
        self.assertEqual(trace["repository_commits"], commits)
        self.assertEqual(trace["packet_checksums"], [packet["checksum"]])
        self.assertEqual(trace["integrity_rejected"], 0)
        provenance = json.loads(trace["outputs"][0]["text"])
        self.assertEqual(provenance["runtime_manifest_sha256"], "d" * 64)
        self.assertEqual(provenance["repository_commits"], commits)


if __name__ == "__main__":
    unittest.main()
