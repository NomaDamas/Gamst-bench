"""Generate operator-reviewed native recipes; no data/model acquisition or execution."""
import json
from pathlib import Path
recipes=[]
def step(id,kind,argv,cwd='{checkout}'):return dict(id=id,kind=kind,argv=argv,cwd=cwd)
def add(id,benchmark,repo,revision,stages,notes,variables=None,environment=None,secrets=None):
 recipes.append(dict(id=id,benchmark=benchmark,source_url='https://github.com/'+repo,runner_revision=revision,stages=stages,notes=notes,variables=variables or {},environment=environment or {},secret_env=secrets or [],validation='source CLI inspected; GPU execution pending'))
py='{python}'
fb='1951dd11b7423cd76998c9f2fb04e71e95a232b1'
for mode,script in [('baseline','eval_qwen3_vl_8b.sh'),('proactive','eval_qwen3_vl_8b_proactive_frame.sh')]:
 # Official entry point combines inference and judge. Separate score marker is not faked;
 # classify a combined stage explicitly below.
 add('fastbench-'+mode,'fastbench','Ashone3/FastBench',fb,[step('native-evaluate','inference_score',['/bin/bash','{checkout}/scripts/'+script,'--model-path','{model}','--video-root','{checkout}','--output-dir','{output}','--run-id',mode,'--num-gpus','1','--num-workers','1','--num-scorers','1'])],
     'Official script combines inference and scoring. Prestart matching local VLM and judge servers; preserve prompt and preset. Full dataset, not smoke. Data layout must match dataset/qa_video.',environment={'HOST':'127.0.0.1','STREAMEVAL_JUDGER_BACKEND':'openai_compatible','STREAMEVAL_JUDGER_API_BASE':'http://127.0.0.1:9000/v1','STREAMEVAL_JUDGER_MODEL':'REPLACE_WITH_PINNED_JUDGE'})
spot=[]
for t in ['ABD','PNR']:
 spot.append(step('infer-'+t.lower(),'inference',[py,'{checkout}/inference.py','--task',t,'--model','QwenVL','--qwen_version','3','--model_path','{model}','--annotation_root','{data}','--video_root','{data}/videos','--result_dir','{output}']))
spot.append(step('score-detection','score',[py,'{checkout}/score.py','--tasks','ABD','PNR','--model','QwenVL','--annotation_root','{data}','--result_dir','{output}']))
add('spot-detection','spot','dibschat/SPOT-Bench','06248474e38e5dd1b6f6f475c882f8975d3a400b',spot,'Detection ABD+PNR only. Interaction/Intervention are partial release and need separate judge/access profiles. All streaming outputs remain in native traces.')
add('ovo-offline','ovo','JoeLeelyf/OVO-Bench','c34093f9a072d93f9e1c6b923446dfba71f4528e',[
 step('infer','inference',[py,'{checkout}/inference.py','--mode','offline','--model','QWen2VL_7B','--model_path','{model}','--anno_path','{data}/ovo_bench_new.json','--video_dir','{data}/src_videos','--chunked_dir','{data}/chunked_videos','--result_dir','{output}']),
 step('score','score',[py,'{checkout}/score.py','--mode','offline','--model','QWen2VL_7B','--result_dir','{output}'])],
 'All 12 tasks. Use the actual QWen2VL_7B result directory from utils/OVOBench.py, correcting the stale underscore in the example shell wrapper. Offline baseline is not a streaming Gamst hybrid. Online models need their own OVOBenchOnline implementation.')
for mode in ['probe','online']:
 add('omnipro-'+mode,'omnipro','RuixiangZhao/OmniPro','7c72e8117f180bf9a22320c1dc2c005bbe4c4a0f',[
  step('infer','inference',[py,'{checkout}/scripts/run_'+mode+'.py','--model','{native_model}','--model_path','{model}','--data_path','{data}/benchmark.json','--num_gpus','1','--output_dir','{output}','--no_resume']),
  step('score','score',[py,'{checkout}/scripts/'+('compute_metrics.py' if mode=='probe' else 'compute_online_metrics.py'),'--pred_dir','{output}','--tolerance','3'])],
  'Probe and online metrics remain separate. Pin judge where content judging is required. Audio ablations use separate profiles and native model names; audio/video paths must match the original data layout.',variables={'native_model':'qwen2.5-omni' if mode=='probe' else 'minicpm-o'})
add('streamarena-offline','streamarena','JIA-Lab-research/StreamArena','ec0325b9552b045c2e53afbf425315ce867313ee',[
 step('infer','inference',['/bin/bash','{checkout}/method/offline/scripts/run_qwen.sh']),
 step('score','score',['/bin/bash','{checkout}/judge/scripts/run_judge.sh','{output}/records.jsonl'])],
 'Offline RTP/HR/Tool only; does not test Pro. Tool search and judge may transmit content externally: review endpoints explicitly. StreamMind continuous/proactive recipe is separate.',
 environment={'BASE_URL':'http://127.0.0.1:8000/v1','MODEL':'REPLACE_WITH_SERVED_MODEL','DATASET':'{data}/question.en.jsonl','VIDEO_DIR':'{data}/videos','OUT':'{output}/records.jsonl','AUTO_JUDGE':'0','JUDGE_URL':'REPLACE_WITH_REVIEWED_JUDGE_ENDPOINT','JUDGE_MODEL':'REPLACE_WITH_PINNED_JUDGE','CONCURRENCY':'1'},secrets=['JUDGE_API_KEY','SERPER_API_KEY'])
add('streamarena-continuous','streamarena','JIA-Lab-research/StreamArena','ec0325b9552b045c2e53afbf425315ce867313ee',[
 step('infer','inference',['/bin/bash','{checkout}/method/streammind/scripts/run_streammind.sh']),
 step('score','score',['/bin/bash','{checkout}/judge/scripts/run_judge.sh','{output}/records.jsonl'])],
 'Continuous multi-turn/proactive driver. Install/configure the upstream StreamMind agent and its model endpoints. A Gamst agent must implement the same StreamingAgent interface and use a separate gamst-extension profile; do not relabel StreamMind output as Gamst.',
 environment={'AGENT':'REPLACE_WITH_INSTALLED_AGENT_CLASS','DATASET':'{data}/question.en.jsonl','VIDEO_DIR':'{data}/videos','OUT':'{output}/records.jsonl','FPS':'2','ASR_URL':'REPLACE_WITH_LOCAL_ASR_ENDPOINT','JUDGE_URL':'REPLACE_WITH_REVIEWED_JUDGE_ENDPOINT','JUDGE_MODEL':'REPLACE_WITH_PINNED_JUDGE','CONCURRENCY':'1'},secrets=['JUDGE_API_KEY','SERPER_API_KEY'])
stages=[]
for task,bench in [('real','Streaming'),('omni','Streaming'),('sqa','StreamingSQA'),('proactive','StreamingProactive')]:
 stages.append(step('infer-'+task,'inference',[py,'{checkout}/src/eval.py','--model_name','MiniCPM-V','--benchmark_name',bench,'--data_file','{data}/questions_'+task+'.json','--output_file','{output}/'+task+'.json','--context_time','60'],cwd='{checkout}/src'))
 stages.append(step('score-'+task,'score',[py,'{checkout}/src/data/count.py','--model','MiniCPM-V','--task',task,'--src','{output}/'+task+'.json'],cwd='{checkout}/src/data'))
add('streamingbench-regression','streamingbench','THUNLP-MT/StreamingBench','89299232c4cc1cc3721951173c5f107b48cf6877',stages,'Native MiniCPM-V baseline. Configure/pin its model loader to local downloaded weights before enabling; if code changes commit the patch and mark protocol differences. Omni support must be real, not vision silently substituted. 60-second context distinct from all-context scores.')
add('infstreams-long','infstreams','mit-han-lab/streaming-vlm','a940d8cbfa14eefe651b7f4adeb81825c28cc6c6',[
 step('generate','inference',[py,'{checkout}/streaming_vlm/eval/model_compete/generate_segments.py','--model_path','{model}','--model_base','Qwen','--eval_metadata','{data}/eval_all_metadata.jsonl','--start_time','1000','--duration','10000','--temperature','0.9','--start_line','0','--end_line','{total_lines}','--out_dir','{output}/answers/result_0.jsonl','--query','{caption_prompt}']),
 step('merge','prepare',[py,'{checkout}/streaming_vlm/eval/model_compete/merge_result.py','--shard_dir','{output}/answers']),
 step('score','score',[py,'{checkout}/streaming_vlm/eval/model_compete/score_segments.py','--merged_a','{output}/answers/merged_result.jsonl','--merged_b','{data}/baseline/merged_result.jsonl','--score_metadata','{data}/temp_score_clips.jsonl','--judge_model','{judge_model}','--start_line','0','--end_line','{score_lines}','--out_path','{output}/scores/score_segments_0.jsonl']),
 step('merge-score','score',[py,'{checkout}/streaming_vlm/eval/model_compete/merge_score.py','--pair_dir','{output}/scores'])],
 'VSAS-compatible fallback only; never report this output as an official VSAS-Bench score. Direct single-shard entry points avoid upstream hardcoded NFS paths and eight-GPU shell defaults. Preserve original caption prompt and paired baseline. Inspect effective duration/context semantics; a run timeout does not establish a completed long session. Judge requires explicit endpoint/data-transfer review.',
 variables={'total_lines':'REPLACE_WITH_METADATA_LINE_COUNT','score_lines':'REPLACE_WITH_SCORE_METADATA_LINE_COUNT','caption_prompt':'REPLACE_WITH_VERIFIED_ORIGINAL_PROMPT','judge_model':'REPLACE_WITH_PINNED_JUDGE'},environment={'EVAL_DATASET_PATH':'{data}'},secrets=['OPENAI_API_KEY'])
Path('mcp/recipes.json').write_text(json.dumps(recipes,indent=2)+'\n')
# Disabled deployment templates are operator config, not tool-controlled shell commands.
profiles={}
for r in recipes:
 checkout='/srv/benchmarks/'+r['benchmark'];python='/srv/venvs/'+r['benchmark']+'/bin/python'
 def subst(v):
  if isinstance(v,str):return v.replace('{checkout}',checkout).replace('{python}',python)
  if isinstance(v,list):return [subst(x) for x in v]
  if isinstance(v,dict):return {k:subst(x) for k,x in v.items()}
  return v
 profiles[r['id']]={**{k:r[k] for k in ('benchmark','source_url','runner_revision','notes')},'enabled':False,'track':'official','metric':'REPLACE_WITH_NATIVE_METRIC','split':'REPLACE_WITH_RELEASE_SPLIT','mode':r['id'],'hardware':'REPLACE_WITH_GCE_HARDWARE','model':'REPLACE_WITH_MODEL_ID','model_revision':'REPLACE_WITH_40_CHAR_MODEL_COMMIT','dataset_revision':'REPLACE_WITH_40_CHAR_DATA_COMMIT','checkout':checkout,'dataset_root':'/srv/data/'+r['benchmark'],'dataset_manifest':'/srv/manifests/'+r['benchmark']+'.json','dataset_manifest_sha256':None,'model_path':'/srv/models/REPLACE_WITH_MODEL_SNAPSHOT','hf_executable':str(Path(python).parent/'hf'),'output_dirs':['answers','scores'] if r['benchmark']=='infstreams' else [],'timeout_seconds':14400,'data_access_reviewed':False,'execution_reviewed':False,'stage_outputs_reviewed':False,'stages':subst(r['stages']),'variables':r['variables'],'environment':{'PATH':str(Path(python).parent)+':/usr/local/bin:/usr/bin:/bin',**r['environment']},'secret_env':r['secret_env']}
Path('mcp/profiles.example.json').write_text(json.dumps({'schema_version':1,'project_id':'REPLACE_WITH_VERIFIED_PROJECT_ID','runs_root':'/srv/gamst-runs','profiles':profiles},indent=2)+'\n')
