import asyncio,copy,json,sys,tempfile,unittest
from pathlib import Path
from gamst_bench.contracts import freeze,digest,validate_plan,read,write_new
from gamst_bench.fixtures import make_fixture
from gamst_bench.scoring import evaluate,score_row,summarize,comparison
from gamst_bench.collect import run_task,collect
from gamst_bench.soak import soak
from gamst_bench.adapters.gamst_http import request_chat

class ProtocolTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.fixture=make_fixture()
 def setUp(self):self.plan,self.traces,self.grades,self.report=copy.deepcopy(self.fixture)
 def update_trace(self,index=0):
  t=self.traces[index];t['trace_sha256']=digest({k:v for k,v in t.items() if k!='trace_sha256'});self.grades[index]['trace_sha256']=t['trace_sha256']
 def row(self,index=0):
  t=self.traces[index];task=next(tk for tk in self.plan['tasks'] if tk['id']==t['task_id']);return score_row(self.plan,task,t,self.grades[index])
 def test_synthetic_never_passes_acceptance(self):
  self.assertEqual(self.report['acceptance'],'not_established');self.assertTrue(all(c['status']=='not_passed' for c in self.report['comparisons']))
 def test_plan_mutation_rejected(self):
  self.plan['consumer_model']='changed'
  with self.assertRaisesRegex(ValueError,'changed after freeze'):validate_plan(self.plan)
 def test_input_hash_covers_prompt(self):
  self.plan['tasks'][0]['query']='edited'
  with self.assertRaisesRegex(ValueError,'input digest'):validate_plan(self.plan)
 def test_split_leakage(self):
  self.plan['tasks'][1]['session_id']=self.plan['tasks'][0]['session_id'];self.plan['tasks'][1]['split']='dev'
  with self.assertRaisesRegex(ValueError,'split leakage'):freeze(self.plan)
 def test_incomplete_pairs_fail(self):
  with self.assertRaisesRegex(ValueError,'missing runs'):evaluate(self.plan,self.traces[:-1],self.grades)
 def test_duplicate_runs_fail(self):
  with self.assertRaisesRegex(ValueError,'duplicate'):evaluate(self.plan,self.traces+[self.traces[0]],self.grades)
 def test_assessment_binds_trace(self):
  self.grades[0]['trace_sha256']='wrong'
  with self.assertRaisesRegex(ValueError,'exact trace'):self.row()
 def test_unknown_evidence_rejected(self):
  self.grades[0]['evidence_ids']=['invented']
  with self.assertRaisesRegex(ValueError,'nonexistent evidence'):self.row()
 def test_early_answer_is_not_success(self):
  self.traces[1]['answer_ready_ms']=1000;self.traces[1]['outputs'][-1]['received_ms']=1000;self.grades[1]['evidence_ids']=[];self.update_trace(1)
  row=self.row(1);self.assertTrue(row['early']);self.assertEqual(row['quality'],0)
 def test_timeout_penalty_and_failure_denominator(self):
  self.traces[1]['status']='timeout';self.traces[1]['answer_ready_ms']=None;self.traces[1]['outputs']=[];self.update_trace(1)
  row=self.row(1);self.assertEqual(row['latency_ms'],self.plan['timeout_ms']);self.assertFalse(row['success']);self.assertEqual(summarize([row])['tasks'],1)
 def test_known_price_does_not_imply_complete_cost(self):
  self.grades[1]['accounting_complete']=False;self.assertIsNone(self.row(1)['cost_usd'])
 def test_absent_rate_is_unknown(self):
  self.plan['rate_card']={};self.plan=freeze(self.plan)
  for i,t in enumerate(self.traces):t['plan_sha256']=self.plan['plan_sha256'];self.update_trace(i)
  self.assertIsNone(self.row()['cost_usd'])
 def test_first_answer_boundary_cannot_be_replaced(self):
  self.traces[1]['answer_ready_ms']+=100;self.update_trace(1)
  with self.assertRaisesRegex(ValueError,'first final answer'):self.row(1)
 def test_unsupported_claim_defeats_grounding(self):
  self.grades[1]['unsupported_claims']=1
  self.assertEqual(self.row(1)['quality'],0)
 def test_correct_abstention_requires_unanswerable_task(self):
  self.grades[1]['abstained']=True;self.assertEqual(self.row(1)['quality'],0)
 def test_cluster_count_is_sessions_not_frames(self):
  rows=copy.deepcopy(self.report['rows'])
  for row in rows:row['session_id']='one-session'
  c=comparison(self.plan,rows,'A','C');self.assertEqual(c['clusters'],1);self.assertFalse(c['gates']['enough_sessions'])
 def test_bootstrap_is_reproducible(self):
  self.assertEqual(comparison(self.plan,self.report['rows'],'A','C'),self.report['comparisons'][0])
 def test_atomic_output_refuses_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'result.json';write_new(path,{'ok':True})
   with self.assertRaises(FileExistsError):write_new(path,{'ok':False})
 def test_duplicate_json_keys_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.json';p.write_text('{"x":1,"x":2}')
   with self.assertRaisesRegex(ValueError,'duplicate JSON'):read(p)
 def test_remote_adapter_requires_explicit_authorization(self):
  with self.assertRaisesRegex(ValueError,'remote transmission'):request_chat('https://example.com/v1','model',[])
 def test_context_before_query_is_counted(self):
  task=self.plan['tasks'][0];task['query_ms']=task['available_ms']+1000
  trace=self.traces[0];grade=self.grades[0]
  trace['outputs'].insert(0,{'type':'context','received_ms':task['available_ms']+50,'evidence_ids':grade['evidence_ids']})
  self.update_trace();self.assertEqual(self.row()['context_latency_ms'],50)
 def test_sweep_configuration_cannot_be_acceptance_arm(self):
  self.plan['baseline']='C3'
  with self.assertRaisesRegex(ValueError,'primary baseline'):freeze(self.plan)
 def test_every_control_is_compared_to_candidate(self):
  self.assertEqual([c['baseline'] for c in self.report['comparisons']],[self.plan['baseline'],*self.plan['controls']])
 def test_mismatched_sensor_track_rejected(self):
  self.plan['systems'][0]['sensor_track']='different'
  with self.assertRaisesRegex(ValueError,'sensor tracks'):freeze(self.plan)
 def test_official_score_cannot_attach_to_synthetic(self):
  from gamst_bench.external import attach_official
  score=dict(metric='timed QA',split='test',evaluation_mode='online',benchmark='FastBench',protocol_revision='1',dataset_revision='1',scorer_revision='1',system_id='A',score=50,scale=100,artifact_sha256='a'*64,source_url='https://example.com/result',configuration_sha256=digest(self.report['systems'][0]),protocol_modified=False)
  with self.assertRaisesRegex(ValueError,'synthetic'):attach_official(self.report,score)
 def test_local_chat_contract(self):
  import threading
  from http.server import BaseHTTPRequestHandler,HTTPServer
  requests=[]
  class Handler(BaseHTTPRequestHandler):
   def do_POST(self):
    requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
    self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'choices':[{'message':{'content':'observed'}}],'usage':{'prompt_tokens':10,'completion_tokens':2}}).encode())
   def log_message(self,*args):pass
  server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.handle_request);thread.start()
  try:
   text,usage=request_chat('http://127.0.0.1:'+str(server.server_port)+'/v1','pinned-model',[{'role':'user','content':'test'}])
   self.assertEqual(text,'observed');self.assertEqual(usage['prompt_tokens'],10);self.assertEqual(requests[0]['model'],'pinned-model')
  finally:thread.join(timeout=2);server.server_close()
 def test_negative_usage_rejected(self):
  self.traces[1]['cost_quantities']['vlm']=-1;self.update_trace(1)
  with self.assertRaises(ValueError):self.row(1)

class CollectorTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.plan,_,_,_=make_fixture();task=self.plan['tasks'][0]
  task.update(duration_ms=100,query_ms=50,available_ms=0,deadline_ms=100)
  task['inputs']=task['inputs'][:1];self.plan['tasks']=[task];self.plan['timeout_ms']=1000;self.plan=freeze(self.plan)
  self.command=[sys.executable,str(Path('tests/echo_adapter.py').resolve())]
 async def test_causal_collection_and_hash(self):
  trace=await run_task(self.plan,self.plan['systems'][0],self.plan['tasks'][0],self.command)
  self.assertEqual(trace['status'],'success');self.assertEqual(trace['clock'],'wall');self.assertTrue(trace['synthetic'])
  self.assertGreaterEqual(trace['answer_ready_ms'],50)
  self.assertEqual(trace['trace_sha256'],digest({k:v for k,v in trace.items() if k!='trace_sha256'}))
 async def test_documented_direct_media_blob_is_materialized(self):
  import hashlib
  raw=b'jpeg-fixture'
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'image.jpg';path.write_bytes(raw)
   task=self.plan['tasks'][0];task['inputs']=[dict(task['inputs'][0],payload={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'field':'jpeg_base64'})]
   self.plan=freeze(self.plan)
   trace=await run_task(self.plan,self.plan['systems'][0],task,self.command+['--require-jpeg'])
   self.assertEqual(trace['status'],'success')
 async def test_hung_process_records_timeout(self):
  trace=await run_task(self.plan,self.plan['systems'][0],self.plan['tasks'][0],self.command+['--hang'])
  self.assertEqual(trace['status'],'timeout')
 async def test_malformed_output_is_failure(self):
  trace=await run_task(self.plan,self.plan['systems'][0],self.plan['tasks'][0],self.command+['--bad'])
  self.assertEqual(trace['status'],'error')
 async def test_collect_retains_every_pair(self):
  with tempfile.TemporaryDirectory() as d:
   result=await collect(self.plan,{s['id']:self.command for s in self.plan['systems']},Path(d)/'run')
   n=len(self.plan['systems']);self.assertEqual(result['traces'],n);self.assertEqual(len(read(Path(d)/'run/traces.json')),n)
 async def test_spawn_failure_preserves_all_pairs(self):
  with tempfile.TemporaryDirectory() as d:
   await collect(self.plan,{s['id']:['/does-not-exist/gamst-adapter'] for s in self.plan['systems']},Path(d)/'run')
   traces=read(Path(d)/'run/traces.json');self.assertEqual(len(traces),len(self.plan['systems']))
   self.assertTrue(all(t['status']=='error' and 'spawn_failed' in t['diagnostics'] for t in traces))
 async def test_short_soak_is_not_quality_acceptance(self):
  with tempfile.TemporaryDirectory() as d:
   result=await soak(self.plan,{'A':self.command},'A',.2,Path(d)/'soak')
   self.assertFalse(result['quality_acceptance']);self.assertEqual(result['status'],'completed')

if __name__=='__main__':unittest.main()
