import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from gamst_bench.contracts import digest,write_new
from gamst_bench.mcp_jobs import (Jobs,catalog,validate_profile,expand,ROOT,
                                  recipe_metadata,recipe_summary)
from gamst_bench.mcp_worker import execute,preflight


def profile(root):
 return dict(benchmark='fastbench',enabled=True,track='official',runner_revision='a'*40,dataset_revision='b'*40,model_revision='c'*40,
 dataset_manifest_sha256='d'*64,metric='T-F1',split='detection',mode='online',hardware='test-only',model='stub-not-a-model',source_url='https://example.com',
 timeout_seconds=10,data_access_reviewed=True,execution_reviewed=True,stage_outputs_reviewed=True,checkout=str(root),dataset_root=str(root),dataset_manifest=str(root/'files.json'),model_path=str(root),
 stages=[dict(id='infer',kind='inference',argv=[sys.executable,str(root/'stub.py')],cwd=str(root)),dict(id='score',kind='score',argv=[sys.executable,str(root/'stub.py')],cwd=str(root))],environment={},secret_env=[])


class JobsTests(unittest.TestCase):
 def setUp(self):
  base=ROOT/'runs/test-temporary';base.mkdir(parents=True,exist_ok=True)
  self.tmp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  self.p=profile(self.root);self.jobs=Jobs(dict(profiles={'fastbench':self.p},runs_root=str(self.root/'runs'),project_id='gamst-project'))
 def test_three_core_families_have_recipes(self):
  items=catalog();supported=[b for b in items if b['mcp_support']=='registered native runner']
  self.assertEqual({b['id'] for b in supported},{'fastbench','omnipro','streamarena'})
  for b in supported:
   self.assertTrue(b['recipes']);self.assertFalse(b['gpu_validated'])
   self.assertEqual(b['recipe_summary']['executable'],len(b['recipes']))
   self.assertEqual(b['recipe_summary']['reference_only'],0)

 def test_recipe_metadata_exposes_executable_boundary(self):
  recipes=json.loads((ROOT/'mcp'/'recipes.json').read_text())
  summary=recipe_summary(recipes)
  self.assertEqual(summary['total'],10)
  self.assertEqual(summary['executable'],6)
  self.assertEqual(summary['reference_only'],4)
  self.assertEqual(set(summary['executable_ids']),{
   'fastbench-baseline','fastbench-proactive','omnipro-probe',
   'omnipro-online','streamarena-offline','streamarena-continuous'})
  reference=recipe_metadata(next(r for r in recipes if r['id']=='spot-detection'))
  self.assertFalse(reference['executable'])
  self.assertEqual(reference['mcp_support'],'reference only')
  self.assertTrue(reference['blocker'])
 def test_environment_planning_has_no_execution_side_effect(self):
  local=self.jobs.environment('local');self.assertFalse(local['execution_allowed']);self.assertFalse(local['side_effects']);self.assertTrue(local['commands'])
  gcp=self.jobs.environment('gcp',project_id='gamst-project');self.assertFalse(gcp['execution_allowed']);self.assertTrue(any('gcloud'==c[0] for c in gcp['commands']))
 def test_invalid_environment_target_rejected(self):
  with self.assertRaisesRegex(ValueError,'target'):self.jobs.environment('windows-gpu')
 def test_vsas_is_required_but_not_falsely_executable(self):
  item=next(b for b in catalog() if b['id']=='vsas')
  self.assertTrue(item['required']);self.assertEqual(item['mcp_support'],'required; blocked pending official runner');self.assertEqual(item['recipes'],[])
 def test_local_start_denied_before_spawn_or_output(self):
  plan=self.jobs.plan('fastbench')
  with patch('gamst_bench.mcp_jobs.gce_identity',side_effect=ValueError('not GCE')),patch('gamst_bench.mcp_jobs.subprocess.Popen') as popen:
   with self.assertRaisesRegex(ValueError,'not GCE'):self.jobs.start('fastbench',plan['profile_sha256'])
   popen.assert_not_called();self.assertFalse((self.root/'runs').exists())
 def test_dataset_download_also_refuses_local_execution(self):
  self.jobs.profiles['fastbench']['hf_executable']='/srv/venv/bin/hf'
  plan=self.jobs.plan('fastbench')
  with patch('gamst_bench.mcp_jobs.gce_identity',side_effect=ValueError('not GCE')),patch('gamst_bench.mcp_jobs.subprocess.Popen') as popen:
   with self.assertRaisesRegex(ValueError,'not GCE'):self.jobs.start('fastbench',plan['profile_sha256'],'dataset')
   popen.assert_not_called();self.assertFalse((self.root/'runs').exists())
 def test_dataset_worker_uses_catalog_revision_and_hashes_result(self):
  out=self.prepare_worker();req=json.loads((out/'request.json').read_text())
  data=self.root/'new-data';req['operation']='dataset';req['profile']['dataset_root']=str(data);req['profile']['hf_executable']='/srv/bin/hf'
  req['profile_sha256']=digest(req['profile']);(out/'request.json').write_text(json.dumps(req))
  seen=[]
  class Done:
   returncode=0
   def poll(self):return 0
  def fake_spawn(argv,**kwargs):
   seen.extend(argv);data.mkdir();(data/'fixture.txt').write_text('unit fixture, no remote download');return Done()
  with patch('gamst_bench.mcp_worker.preflight',return_value={}),patch('gamst_bench.mcp_worker.subprocess.Popen',side_effect=fake_spawn):execute(out)
  self.assertEqual(json.loads((out/'status.json').read_text())['status'],'data_downloaded_review_required')
  self.assertIn('Ashenone3/FastBench',seen);self.assertIn('b'*40,seen)
  self.assertEqual(len(json.loads((out/'dataset-files.json').read_text())),1)
 def test_manifest_is_frozen_before_evaluation_but_not_download(self):
  self.jobs.profiles['fastbench']['dataset_manifest_sha256']=None
  self.assertTrue(self.jobs.plan('fastbench')['blockers'])
  self.assertFalse(self.jobs.plan('fastbench','dataset')['blockers'])
  manifest=[{'path':'fixture.txt','sha256':'0'*64}]
  (self.root/'files.json').write_text(json.dumps(manifest))
  p=copy.deepcopy(self.p);p['dataset_manifest_sha256']='0'*64
  req={'profile':p,'profile_sha256':digest(p),'project_id':'gamst-project'}
  with patch('gamst_bench.mcp_worker.gce_identity',return_value={}),patch('gamst_bench.mcp_worker.subprocess.check_output',side_effect=['a'*40,'']):
   with self.assertRaisesRegex(ValueError,'manifest changed'):preflight(req)
 def test_changed_profile_and_disabled_template_refused(self):
  with self.assertRaisesRegex(ValueError,'changed'):self.jobs.start('fastbench','0'*64)
  p=copy.deepcopy(self.p);p['enabled']=False
  with self.assertRaisesRegex(ValueError,'disabled'):validate_profile(p)
  p=copy.deepcopy(self.p);p['variables']={'judge':'REPLACE_ME'}
  with self.assertRaisesRegex(ValueError,'placeholders'):validate_profile(p)
 def test_shell_snippets_and_plaintext_secrets_refused(self):
  for value in ([sys.executable,'-c','print(1)'],['/bin/bash','-c','echo hello']):
   p=copy.deepcopy(self.p);p['stages'][0]['argv']=value
   with self.assertRaisesRegex(ValueError,'inline'):validate_profile(p)
  p=copy.deepcopy(self.p);p['environment']={'API_KEY':'secret'}
  with self.assertRaisesRegex(ValueError,'secret'):validate_profile(p)
 def test_expansion_is_argv_data_not_shell(self):
  self.assertEqual(expand(['--input','{data}'],{'data':'a; echo bad'}),['--input','a; echo bad'])
  with self.assertRaisesRegex(ValueError,'unresolved'):expand('{unknown}',{})
 def test_artifacts_cannot_escape_and_reads_are_bounded(self):
  out=self.root/'runs'/('a'*32);out.mkdir(parents=True);write_new(out/'request.json',{})
  (out/'big.log').write_text('x'*40000);self.assertTrue(self.jobs.read_artifact('a'*32,'big.log')['truncated'])
  (self.root/'private.log').write_text('secret');(out/'link.log').symlink_to(self.root/'private.log')
  with self.assertRaises(ValueError):self.jobs.read_artifact('a'*32,'link.log')
  with self.assertRaises(ValueError):self.jobs.read_artifact('../private','big.log')
 def prepare_worker(self,script='print("unit fixture, no inference")',timeout=10):
  out=self.root/'runs'/('a'*32);out.mkdir(parents=True)
  (self.root/'stub.py').write_text(script)
  p=copy.deepcopy(self.p);p['timeout_seconds']=timeout
  write_new(out/'request.json',{'profile':p,'profile_sha256':digest(p),'project_id':'gamst-project'})
  return out
 def test_worker_stage_completion_is_not_a_score(self):
  out=self.prepare_worker()
  with patch('gamst_bench.mcp_worker.preflight',return_value={'test_fixture':True}),patch('gamst_bench.mcp_worker.gpu_sample',return_value={'raw_csv':None}):execute(out)
  state=json.loads((out/'status.json').read_text())
  self.assertEqual(state['status'],'execution_finished_review_required');self.assertFalse(state['score_verified'])
  self.assertEqual(state['completed'],['infer','score']);self.assertIsNone(json.loads((out/'accounting.json').read_text())['total_pipeline_cost_usd'])
 def test_worker_failure_prevents_later_scoring(self):
  out=self.prepare_worker('raise SystemExit(3)')
  with patch('gamst_bench.mcp_worker.preflight',return_value={}),patch('gamst_bench.mcp_worker.gpu_sample',return_value={}):execute(out)
  self.assertEqual(json.loads((out/'status.json').read_text())['status'],'failed');self.assertFalse((out/'score.log').exists())
 def test_worker_cancellation_and_timeout(self):
  out=self.prepare_worker('import time; time.sleep(5)',timeout=1)
  with patch('gamst_bench.mcp_worker.preflight',return_value={}),patch('gamst_bench.mcp_worker.gpu_sample',return_value={}):execute(out)
  self.assertEqual(json.loads((out/'status.json').read_text())['status'],'timed_out')
 def test_cancel_before_inference(self):
  out=self.prepare_worker();self.jobs.cancel('a'*32)
  with patch('gamst_bench.mcp_worker.preflight',return_value={}):execute(out)
  self.assertEqual(self.jobs.status('a'*32)['status'],'cancelled');self.assertFalse((out/'infer.log').exists())


if __name__=='__main__':unittest.main()
