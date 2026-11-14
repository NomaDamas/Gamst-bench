import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gamst_bench.cloud import command, run, validate_job, verify_files, sha_file
from gamst_bench.external import attach_official
from gamst_bench.contracts import digest

class CloudTests(unittest.TestCase):
 def setUp(self):
  self.job=dict(schema_version=1,benchmark='FastBench',method='baseline',mode='smoke',project_id='gamst-project',checkout='/srv/FastBench',runner_revision='a'*40,model_path='/srv/model',model_revision='b'*40,dataset_revision='c'*40,dataset_manifest='/srv/files.json',data_access_reviewed=True,run_id='smoke-001',base_port=8000,timeout_seconds=60)
 def test_local_execution_fails_before_subprocess_or_output(self):
  with tempfile.TemporaryDirectory() as d,patch('gamst_bench.cloud.gce_identity',side_effect=ValueError('not GCE')),patch('gamst_bench.cloud.subprocess.Popen') as spawn:
   with self.assertRaises(ValueError):run(self.job,str(Path(d)/'out'))
   spawn.assert_not_called();self.assertFalse((Path(d)/'out').exists())
 def test_smoke_never_scores_and_proactive_uses_full_native_preset(self):
  cmd=command(self.job,'/srv/out');self.assertIn('--skip-scoring',cmd);self.assertIn('--num-samples',cmd)
  self.job['method']='proactive';self.assertTrue(command(self.job,'/srv/out')[1].endswith('eval_qwen3_vl_8b_proactive_frame.sh'))
 def test_unresolved_access_and_revisions_block(self):
  for key,value in [('data_access_reviewed',False),('model_revision','main'),('project_id','REPLACE'),('timeout_seconds',0)]:
   job=copy.deepcopy(self.job);job[key]=value
   with self.assertRaises(ValueError):validate_job(job)
 def test_full_requires_pinned_judge(self):
  self.job['mode']='full'
  with self.assertRaises(ValueError):validate_job(self.job)
  self.job.update(judge_model='local-judge',judge_revision='d'*40,judge_port=9000)
  self.assertNotIn('--skip-scoring',command(self.job,'/srv/out'))
 def test_data_hash_and_path_escape(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d).resolve();(root/'dataset').mkdir();p=root/'dataset/proactive_perception_annotations.json';p.write_text('[]')
   manifest=[dict(path=str(p.relative_to(root)),sha256=sha_file(p))]
   self.assertEqual(len(verify_files(root,manifest)),64)
   p.write_text('[1]')
   with self.assertRaisesRegex(ValueError,'hash'):verify_files(root,manifest)
   with self.assertRaisesRegex(ValueError,'outside'):verify_files(root,[dict(path='../escape',sha256='a'*64)])

class OfficialMetricTests(unittest.TestCase):
 def setUp(self):
  system={'id':'A'};self.report=dict(systems=[system],evidence='measured',official_scores=[])
  self.score=dict(benchmark='OmniPro',metric='F1',split='test',evaluation_mode='online',protocol_revision='1',dataset_revision='1',scorer_revision='1',system_id='A',score=20.9,scale=100,artifact_sha256='a'*64,source_url='https://example.com/result',configuration_sha256=digest(system),protocol_modified=False)
 def test_separate_metrics_can_coexist_but_exact_duplicates_fail(self):
  attach_official(self.report,self.score)
  with self.assertRaisesRegex(ValueError,'duplicate'):attach_official(self.report,self.score)
  other=dict(self.score,metric='paired accuracy',evaluation_mode='probe');attach_official(self.report,other)
  self.assertEqual(len(self.report['official_scores']),2)
 def test_unscoped_or_modified_scores_rejected(self):
  for change in ({'metric':''},{'protocol_modified':True}):
   with self.assertRaises(ValueError):attach_official(self.report,dict(self.score,**change))

if __name__=='__main__':unittest.main()
