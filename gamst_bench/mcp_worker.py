"""Persistent serial native-run worker, with cancellation, deadlines and host GPU samples."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from .contracts import read,require,digest,write_new
from .cloud import gce_identity,sha_file
from .mcp_jobs import expand,validate_profile,catalog


def status(out,**values):
    values['updated_unix']=time.time()
    temp=out/'status.next.json';temp.write_text(json.dumps(values,indent=2)+'\n');temp.replace(out/'status.json')


def stop(process):
    # This process group was created by this worker; no pre-existing model/server processes.
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:pass
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    process.wait()


def preflight(request):
    p=request['profile'];validate_profile(p)
    require(digest(p)==request['profile_sha256'],'frozen profile changed')
    identity=gce_identity(request['project_id'])
    if request.get('operation')=='dataset':
        require(not Path(p['dataset_root']).exists(),'dataset destination exists; use a new revision-specific directory')
        require(Path(p['hf_executable']).is_file(),'Hugging Face CLI missing from profile environment')
        return {'identity':identity,'operation':'dataset','gpu':None}
    root=Path(p['checkout']).resolve()
    revision=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    require(revision==p['runner_revision'],'runner commit mismatch')
    require(not subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=no'],text=True).strip(),'tracked runner code modified')
    data_root=Path(p['dataset_root']).resolve();manifest=read(p['dataset_manifest'])
    require(type(manifest) is list and bool(manifest),'dataset manifest must not be empty')
    require(digest(manifest)==p.get('dataset_manifest_sha256'),'dataset manifest changed after plan freeze')
    seen=set()
    for item in manifest:
        name=item['path'];path=(data_root/name).resolve()
        require(not Path(name).is_absolute() and path.is_relative_to(data_root) and path.is_file(),'invalid dataset path')
        require(name not in seen,'duplicate data file');seen.add(name)
        require(sha_file(path)==item['sha256'],'dataset file hash mismatch: '+name)
    require(Path(p['model_path']).is_dir(),'pinned model directory missing')
    for name in p.get('secret_env',[]):require(bool(os.environ.get(name)),'required secret environment missing: '+name)
    return {'identity':identity,'manifest_sha256':digest(manifest),'checkpoint_identity':'declared; review serving process and model file manifest',
            'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=name,uuid,driver_version,memory.total','--format=csv,noheader'],text=True,timeout=10).strip()}


def gpu_sample():
    try:
        raw=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,memory.used,utilization.gpu,power.draw','--format=csv,noheader,nounits'],text=True,stderr=subprocess.DEVNULL,timeout=3).strip()
        return {'raw_csv':raw,'scope':'all host GPUs; includes separate servers; not per-job attribution'}
    except (OSError,subprocess.SubprocessError):return {'raw_csv':None,'scope':'unavailable; not zero'}


def execute(out):
    out=Path(out).resolve();request=read(out/'request.json');process=None;started=time.monotonic()
    with (out.parent/'worker.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            status(out,status='failed',reason='another benchmark owns this run-root worker lock');return
        try:
            status(out,status='preflight')
            evidence=preflight(request);write_new(out/'preflight.json',evidence)
            p=request['profile'];vars={**p.get('variables',{}),'checkout':p['checkout'],'data':p['dataset_root'],'model':p['model_path'],'output':str(out/'native')}
            (out/'native').mkdir()
            downloading=request.get('operation')=='dataset'
            stages=expand(p['stages'],vars)
            if downloading:
                info=next(b for b in catalog() if b['id']==p['benchmark'])
                url=info['dataset_url'];require(url.startswith('https://huggingface.co/datasets/'),'catalog dataset URL required')
                repo=url.removeprefix('https://huggingface.co/datasets/')
                stages=[{'id':'download','kind':'prepare','argv':[p['hf_executable'],'download',repo,'--repo-type','dataset','--revision',p['dataset_revision'],'--local-dir',p['dataset_root']],'cwd':p['checkout']}]
            for name in p.get('output_dirs',[]):
                target=(out/'native'/name).resolve()
                require(target.is_relative_to(out/'native'),'output directory outside run')
                target.mkdir(parents=True,exist_ok=True)
            env={k:os.environ[k] for k in ('PATH','HOME','LD_LIBRARY_PATH','CUDA_VISIBLE_DEVICES') if k in os.environ}
            env.update(expand(p.get('environment',{}),vars))
            env.update({k:os.environ[k] for k in p.get('secret_env',[])})
            if not downloading:env.update({'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'})
            write_new(out/'resolved-stages.json',stages)
            deadline=started+p['timeout_seconds'];completed=[];next_sample=0
            with (out/'resources.jsonl').open('x') as resources:
                for stage in stages:
                    if (out/'cancel.requested').exists():status(out,status='cancelled',completed=completed);return
                    if time.monotonic()>=deadline:status(out,status='timed_out',completed=completed);return
                    cwd=Path(stage['cwd']).resolve()
                    require(cwd.is_relative_to(Path(p['checkout']).resolve()),'stage cwd must stay in pinned checkout')
                    with (out/(stage['id']+'.log')).open('xb') as log:
                        process=subprocess.Popen(stage['argv'],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                        while process.poll() is None:
                            if (out/'cancel.requested').exists():stop(process);status(out,status='cancelled',completed=completed);return
                            if time.monotonic()>=deadline:stop(process);status(out,status='timed_out',completed=completed);return
                            if time.monotonic()>=next_sample:
                                resources.write(json.dumps({'elapsed_seconds':time.monotonic()-started,**gpu_sample()})+'\n');resources.flush()
                                status(out,status='running',stage=stage['id'],completed=completed,elapsed_seconds=time.monotonic()-started)
                                next_sample=time.monotonic()+5
                            time.sleep(.25)
                        require(process.returncode==0,f"stage {stage['id']} failed with exit {process.returncode}")
                        completed.append(stage['id']);process=None
            if downloading:
                root=Path(p['dataset_root']).resolve();files=[]
                for file in root.rglob('*'):
                    if file.is_file() and '.cache' not in file.relative_to(root).parts and '.git' not in file.relative_to(root).parts:
                        require(file.resolve().is_relative_to(root),'downloaded file points outside dataset root')
                        if (out/'cancel.requested').exists():status(out,status='cancelled');return
                        if time.monotonic()>=deadline:status(out,status='timed_out');return
                        files.append({'path':str(file.relative_to(root)),'sha256':sha_file(file)})
                require(bool(files),'download produced no dataset files')
                write_new(out/'dataset-files.json',files)
                status(out,status='data_downloaded_review_required',dataset_revision=p['dataset_revision'],manifest_sha256=digest(files),files=len(files),note='Archive extraction, completeness and access checks remain explicit.')
                return
            elapsed=time.monotonic()-started
            write_new(out/'accounting.json',{'wall_seconds':elapsed,'total_pipeline_cost_usd':None,'stream_hours':None,
                       'note':'GPU samples and elapsed time do not establish complete cost or event latency. Add reviewed prices, server/API usage and event traces.'})
            status(out,status='execution_finished_review_required',completed=completed,elapsed_seconds=elapsed,
                   score_verified=False,official_submission=False,quality_acceptance=False)
        except Exception as e:
            if process is not None and process.poll() is None:stop(process)
            status(out,status='failed',reason=str(e),elapsed_seconds=time.monotonic()-started)

if __name__=='__main__':execute(sys.argv[1])
