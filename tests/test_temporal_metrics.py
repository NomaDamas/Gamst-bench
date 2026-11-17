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

    def test_answer_provenance_cutoff_and_recovery_escalation(self):
        result=temporal_metrics([
            {'type':'context','evidence_provenance':[{'capture_timestamp_ms':200}]},
            {'type':'answer','evidence_provenance':[{'capture_timestamp_ms':50}],
             'recovered':True,'escalated':True,'recovery_ms':12},
        ], query_cutoff_ms=100)
        self.assertEqual(result['query_cutoff_violations'], 0)
        self.assertEqual(result['recovery_events'], 1)
        self.assertEqual(result['escalations'], 1)
        self.assertEqual(result['recovery_ms']['mean_ms'], 12)

if __name__ == '__main__': unittest.main()
