import unittest
from gamst_bench.temporal_metrics import summary, temporal_metrics

class TemporalMetricTests(unittest.TestCase):
    def test_percentiles_and_unknown_empty(self):
        self.assertEqual(summary([]).count, 0)
        self.assertEqual(summary([10, 20, 30]).p95_ms, 30)
    def test_temporal_errors_are_counts_not_scores(self):
        result=temporal_metrics([
            {'age_ms': 20, 'time_to_detect_ms': 50, 'capture_timestamp_ms': 101, 'evidence_ids': ['unknown'], 'stale_error': True, 'dropped': 2}
        ], query_cutoff_ms=100, known_evidence=['known'])
        self.assertEqual(result['query_cutoff_violations'], 1)
        self.assertEqual(result['evidence_id_errors'], 1)
        self.assertEqual(result['stale_state_errors'], 1)
        self.assertEqual(result['dropped_inputs'], 2)

if __name__ == '__main__': unittest.main()
