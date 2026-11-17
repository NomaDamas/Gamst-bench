import unittest

from gamst_bench.costbench import aggregate_costs, select_default


class CostBenchTests(unittest.TestCase):
    def test_missing_cost_remains_unknown(self):
        result = aggregate_costs([{"cost_usd": None, "cost_usd_exact": None}], {})
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["total_usd_exact"])

    def test_component_totals_use_exact_decimal_values(self):
        result = aggregate_costs([
            {"cost_usd": 1.25, "cost_usd_exact": "1.25", "cost_components": {"vlm": "1.10", "consumer": "0.15"}},
            {"cost_usd": 0.75, "cost_usd_exact": "0.75", "cost_components": {"vlm": "0.60", "consumer": "0.15"}},
        ], {"vlm": {"revision": "v1"}})
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["components_usd_exact"], {"consumer": "0.30", "vlm": "1.70"})
        self.assertEqual(result["total_usd_exact"], "2.00")

    def test_default_selection_preserves_unmeasured_boundary(self):
        self.assertEqual(select_default(evidence="synthetic", comparisons=[], candidate="C")["status"], "unmeasured")
        comparison = {"status": "numeric_pass_requires_audit", "audit_status": "approved"}
        self.assertEqual(select_default(evidence="measured", comparisons=[comparison], candidate="C")["selected"], "C")

    def test_exact_total_without_components_is_attributed(self):
        result = aggregate_costs([
            {"cost_usd": 0.5, "cost_usd_exact": "0.50"},
            {"cost_usd": 0.25, "cost_usd_exact": "0.25"},
        ], {})
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["components_usd_exact"], {"unattributed": "0.75"})
        self.assertEqual(result["total_usd_exact"], "0.75")

    def test_empty_components_use_exact_total(self):
        result = aggregate_costs([{"cost_usd": 0.5, "cost_usd_exact": "0.50", "cost_components": {}}], {})
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["total_usd_exact"], "0.50")


if __name__ == "__main__":
    unittest.main()
