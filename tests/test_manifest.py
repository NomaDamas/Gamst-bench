import unittest
from gamst_bench.manifest import freeze_manifest, validate_manifest

class ManifestTests(unittest.TestCase):
    def base(self):
        return {'id':'mac-b','runtime_profile':'mac-lightweight','os':'darwin','arch':'arm64','hardware':'Apple M','python':'3.11','consumer_model':'local','consumer_revision':'r1','prompt_revision':'p1','context_contract':'gamst.temporal.v1','dependency_lock':'sha256:lock','providers':[{'name':'asr','revision':'r','model_revision':'m','license':'Apache-2.0','artifact_sha256':'a'*64}], 'timing':{'clock':'monotonic','capture_timestamps':True,'query_cutoffs':True}}
    def test_freeze_and_validate(self):
        manifest=freeze_manifest(self.base()); self.assertEqual(validate_manifest(manifest)['manifest_sha256'],manifest['manifest_sha256'])
    def test_digest_mutation_rejected(self):
        manifest=freeze_manifest(self.base()); manifest['hardware']='other'
        with self.assertRaisesRegex(ValueError,'digest'): validate_manifest(manifest)
    def test_missing_cutoff_rejected(self):
        value=self.base(); value['timing']['query_cutoffs']=False
        with self.assertRaisesRegex(ValueError, 'schema_version'): validate_manifest(value)

if __name__=='__main__': unittest.main()
