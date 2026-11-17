import unittest
from gamst_bench.profiles import profiles, DEFAULT_ARMS, require_measured

class ProfileTests(unittest.TestCase):
    def test_b_to_e_are_explicit_and_unmeasured(self):
        self.assertEqual([x['id'] for x in profiles()], ['B','C','D','E'])
        self.assertFalse(any(x['measured'] for x in profiles()))
    def test_unmeasured_profile_cannot_claim_result(self):
        with self.assertRaisesRegex(RuntimeError, 'no measured result'):
            require_measured(DEFAULT_ARMS[0])

if __name__ == '__main__': unittest.main()
