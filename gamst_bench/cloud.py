"""GCE-only preflight and a pinned FastBench native-run launcher.

No provisioning, downloads, server startup, scoring interpretation or publication.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import urllib.request
from .contracts import read, require, write_new, digest

SCRIPTS = {'baseline': 'eval_qwen3_vl_8b.sh', 'proactive': 'eval_qwen3_vl_8b_proactive_frame.sh'}


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def metadata(path):
    request = urllib.request.Request('http://169.254.169.254/computeMetadata/v1/' + path,
                                     headers={'Metadata-Flavor': 'Google'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=2) as response:
        require(response.headers.get('Metadata-Flavor') == 'Google', 'GCE metadata required')
        return response.read(4096).decode().strip()


def gce_identity(project):
    actual = metadata('project/project-id')
    require(actual == project, 'GCP project differs from frozen project ID')
    return {'project_id': actual, 'instance_id': metadata('instance/id'),
            'zone': metadata('instance/zone'), 'machine_type': metadata('instance/machine-type')}


def validate_job(job):
    require(job.get('schema_version') == 1, 'cloud job schema must be 1')
    require(job.get('benchmark') == 'FastBench', 'native launcher supports FastBench only')
    require(job.get('method') in SCRIPTS, 'unknown native method')
    require(job.get('mode') in ('smoke', 'full'), 'mode must be smoke or full')
    for field in ('project_id','checkout','model_path','model_revision','dataset_revision','dataset_manifest'):
        require(isinstance(job.get(field), str) and job[field] and 'REPLACE' not in job[field], 'resolve '+field)
    for field in ('runner_revision','model_revision','dataset_revision'):
        require(re.fullmatch(r'[0-9a-f]{40}', job[field]) is not None, 'pin full commit: '+field)
    require(re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]',job['project_id']) is not None, 'unique GCP project ID required')
    require(re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',job.get('run_id','')) is not None, 'safe run ID required')
    require(job.get('data_access_reviewed') is True, 'dataset access review pending')
    require(type(job.get('timeout_seconds')) is int and 1 <= job['timeout_seconds'] <= 14400, 'timeout must be 1..14400 seconds')
    require(type(job.get('base_port')) is int and 1024 <= job['base_port'] <= 65535, 'invalid server port')
    require(Path(job['checkout']).is_absolute() and Path(job['model_path']).is_absolute() and Path(job['dataset_manifest']).is_absolute(), 'absolute cloud paths required')
    if job['mode']=='full':
        require(isinstance(job.get('judge_model'),str) and job['judge_model'], 'full run requires judge model')
        require(re.fullmatch(r'[0-9a-f]{40}', job.get('judge_revision','')) is not None, 'pin judge revision')
        require(type(job.get('judge_port')) is int and 1024 <= job['judge_port'] <= 65535, 'local judge port required')
    return job


def command(job, output):
    validate_job(job)
    argv = ['/bin/bash', str(Path(job['checkout'])/'scripts'/SCRIPTS[job['method']]),
            '--model-path',job['model_path'],'--video-root',job['checkout'],
            '--num-gpus','1','--num-workers','1','--num-scorers','1',
            '--base-port',str(job['base_port']),'--run-id',job['run_id'],
            '--output-dir',str(Path(output).resolve()/'native')]
    if job['mode']=='smoke': argv += ['--num-samples','1','--skip-scoring']
    return argv


def verify_files(root, manifest):
    require(type(manifest) is list and len(manifest)>0, 'nonempty dataset file manifest required')
    seen=set()
    for item in manifest:
        name=item['path'];path=(root/name).resolve()
        require(not Path(name).is_absolute() and path.is_relative_to(root) and path.is_file(), 'dataset file outside checkout or missing')
        require(name not in seen, 'duplicate dataset path');seen.add(name)
        require(sha_file(path)==item['sha256'], 'dataset file hash mismatch: '+name)
    require('dataset/proactive_perception_annotations.json' in seen, 'annotation file missing from manifest')
    return digest(manifest)


def run(job, output):
    argv=command(job,output)
    # Fail before touching any model/data or creating output on a local machine.
    identity=gce_identity(job['project_id'])
    root=Path(job['checkout']).resolve()
    revision=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    require(revision==job['runner_revision'], 'native runner revision mismatch')
    require(not subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=no'],text=True).strip(), 'native tracked source has local modifications')
    manifest_sha=verify_files(root,read(job['dataset_manifest']))
    require(Path(job['model_path']).is_dir(), 'downloaded checkpoint missing; launcher does not download models')
    gpu=subprocess.check_output(['nvidia-smi','--query-gpu=name,uuid,driver_version,memory.total','--format=csv,noheader'],text=True).strip()
    require(gpu, 'GPU inventory missing')
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    # Explicit environment avoids hidden EXTRA_ARGS/config overrides and credentials in provenance.
    env={k:os.environ[k] for k in ('PATH','HOME','VIRTUAL_ENV','LD_LIBRARY_PATH','CUDA_VISIBLE_DEVICES') if k in os.environ}
    env.update({'HOST':'127.0.0.1','NUM_GPUS':'1','NUM_WORKERS':'1','NUM_SCORERS':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'})
    if job['mode']=='full':
        env.update({'STREAMEVAL_JUDGER_BACKEND':'openai_compatible','STREAMEVAL_JUDGER_API_BASE':f"http://127.0.0.1:{job['judge_port']}/v1",'STREAMEVAL_JUDGER_MODEL':job['judge_model']})
        if 'STREAMEVAL_JUDGER_API_KEY' in os.environ: env['STREAMEVAL_JUDGER_API_KEY']=os.environ['STREAMEVAL_JUDGER_API_KEY']
    evidence={'job':job,'job_sha256':digest(job),'identity':identity,'gpu':gpu,'dataset_manifest_sha256':manifest_sha,'argv':argv,'started_unix':time.time(),
              'scope':'Native runner execution only. Checkpoint identity is declared, not independently attested; results require scorer and protocol review.'}
    write_new(out/'launch.json',evidence)
    started=time.monotonic();timed_out=False
    with (out/'process.log').open('xb') as log:
        process=subprocess.Popen(argv,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try: code=process.wait(timeout=job['timeout_seconds'])
        except subprocess.TimeoutExpired:
            timed_out=True
            # Only the process group created by this launcher, never existing servers.
            os.killpg(process.pid,signal.SIGTERM)
            try: code=process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);code=process.wait()
    result={'returncode':code,'timed_out':timed_out,'elapsed_seconds':time.monotonic()-started,
            'status':'execution_finished_review_required' if code==0 and not timed_out else 'failed',
            'scored':False,'note':'Exit code is not a benchmark score. Preserve and review native artifacts.'}
    write_new(out/'completion.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description='GCE-only FastBench launcher. Default: validate/print only; no inference.')
    p.add_argument('--job',required=True);p.add_argument('--out',required=True);p.add_argument('--execute',action='store_true')
    a=p.parse_args();job=read(a.job)
    if a.execute:
        result=run(job,a.out);print(json.dumps(result,indent=2))
        if result['status']=='failed':raise SystemExit(1)
    else:print(json.dumps({'executed':False,'argv':command(job,a.out),'requirements':['Matching GCE project','Clean pinned runner','Hashed licensed data','Existing pinned local model/judge servers']},indent=2))

if __name__=='__main__':main()
