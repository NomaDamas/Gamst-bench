"""Registered, immutable benchmark jobs. Only worker execution requires GCE."""
import copy
import json
import os
import platform
import shutil
from pathlib import Path
import re
import subprocess
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1]
from .contracts import read, require, digest, write_new
from .cloud import gce_identity

CORE_BENCHMARKS=('fastbench','omnipro','streamarena','vsas')
EXECUTABLE_BENCHMARKS=('fastbench','omnipro','streamarena')
SUPPORTED=set(EXECUTABLE_BENCHMARKS)
TOKEN=re.compile(r'\{([a-z_]+)\}')


def catalog():
    c=read(ROOT/'data/catalog.json')
    recipes=read(ROOT/'mcp/recipes.json')
    return [{**b,'mcp_support':'registered native runner' if b['id'] in SUPPORTED else 'required; blocked pending official runner' if b.get('required') else 'reference only',
             'recipes':[r['id'] for r in recipes if r['benchmark']==b['id']],
             'gpu_validated':False} for b in c['benchmarks']]


def expand(value, variables):
    if isinstance(value,str):
        def replace(m):
            require(m[1] in variables,'unresolved variable: '+m[1])
            return str(variables[m[1]])
        return TOKEN.sub(replace,value)
    if isinstance(value,list):return [expand(v,variables) for v in value]
    if isinstance(value,dict):return {k:expand(v,variables) for k,v in value.items()}
    return value


def validate_profile(p, enabled=True):
    require(p.get('benchmark') in SUPPORTED,'benchmark has no executable integration')
    require(not enabled or p.get('enabled') is True,'profile disabled until setup review')
    require(p.get('track') in ('official','gamst-extension'),'declare separate evaluation track')
    for key in ('runner_revision','dataset_revision','model_revision'):
        require(re.fullmatch('[a-f0-9]{40}',p.get(key,'')) is not None,'pin '+key)
    for key in ('metric','split','mode','hardware','model','source_url'):
        require(isinstance(p.get(key),str) and p[key] and 'REPLACE' not in p[key],'resolve '+key)
    require(type(p.get('timeout_seconds')) is int and 1<=p['timeout_seconds']<=43200,'timeout must be 1..43200')
    require(p.get('data_access_reviewed') is True,'dataset permission review pending')
    require(p.get('execution_reviewed') is True,'review dependencies, model interface, external calls and scorer')
    require(p.get('stage_outputs_reviewed') is True,'review that stage output files are isolated under run output')
    for key in ('checkout','dataset_root','dataset_manifest','model_path'):
        require(Path(p.get(key,'')).is_absolute() and 'REPLACE' not in p[key],'absolute '+key+' required')
    require(type(p.get('stages')) is list and 1<=len(p['stages'])<=32,'bounded nonempty stages required')
    ids=set()
    for s in p['stages']:
        require(re.fullmatch('[a-z0-9-]{1,40}',s.get('id','')) is not None and s['id'] not in ids,'invalid/duplicate stage ID');ids.add(s['id'])
        require(s.get('kind') in ('inference','score','prepare','inference_score'),'invalid stage kind')
        require(isinstance(s.get('argv'),list) and len(s['argv'])>1 and all(isinstance(a,str) and a for a in s['argv']),'argv list required')
        require(Path(s['argv'][0]).is_absolute(),'absolute executable required')
        require(Path(s.get('cwd','')).is_absolute(),'absolute stage cwd required')
        require(not any(a in ('-c','--command') for a in s['argv']),'inline shell/code is not a registered runner')
        require(not any('api-key' in a.lower() or 'api_key' in a.lower() for a in s['argv']),'credentials belong in named environment variables')
    require(any(s['kind'] in ('inference','inference_score') for s in p['stages']),'inference stage required')
    require(any(s['kind'] in ('score','inference_score') for s in p['stages']),'scoring stage required')
    require(type(p.get('environment',{})) is dict and all(isinstance(k,str) and isinstance(v,str) for k,v in p.get('environment',{}).items()),'invalid environment')
    require(not any(re.search('KEY|TOKEN|SECRET|PASSWORD',k,re.I) for k in p.get('environment',{})),'use secret_env names instead of plaintext secrets')
    require(type(p.get('secret_env',[])) is list and all(re.fullmatch('[A-Z][A-Z0-9_]*',k) for k in p.get('secret_env',[])),'invalid secret names')
    require('REPLACE' not in json.dumps(p),'resolve all template placeholders')
    return p



class Jobs:
    def __init__(self,config=None):
        self.config=copy.deepcopy(config or {'profiles':{},'runs_root':str(ROOT/'runs/mcp'),'project_id':''})
        self.root=Path(self.config['runs_root']).resolve()
        require(self.root.is_absolute(),'absolute runs root required')
        self.profiles=self.config.get('profiles',{})
        require(type(self.profiles) is dict,'profiles must be a map')
    def environment(self,target='local',install=False,project_id=None,region='us-central1'):
        require(target in ('local','gcp'),'target must be local or gcp')
        host={'os':platform.system().lower(),'architecture':platform.machine(),'python':platform.python_version(),
              'gpu':shutil.which('nvidia-smi') is not None,'uv':shutil.which('uv') is not None,
              'gcloud':shutil.which('gcloud') is not None}
        if target=='local':
            root=str((ROOT/'.venv-mcp').resolve());python=f'{root}/bin/python'
            commands=[['python3','-m','venv',root],['python3','-m','pip','install','-r',str(ROOT/'requirements-mcp.txt')]]
            return {'target':'local','host':host,'install_requested':install,'side_effects':install,'commands':commands,
                    'execution_allowed':False,'reason':'Local benchmark inference and dataset downloads are disabled; this prepares only MCP tooling.','python':python}
        require(project_id or self.config.get('project_id'),'project_id required for GCP plan')
        project=project_id or self.config['project_id']
        commands=[['gcloud','compute','instances','create','gamst-bench-gpu','--project',project,'--zone',region+'-a','--machine-type','g2-standard-8','--accelerator','type=nvidia-l4,count=1','--maintenance-policy','TERMINATE','--restart-on-failure=no'],
                  ['gcloud','compute','ssh','gamst-bench-gpu','--project',project,'--zone',region+'-a','--command','git clone --revision PINNED_COMMIT REPO /srv/gamst-bench && uv venv /srv/gamst-mcp --python 3.12 && uv pip install --python /srv/gamst-mcp/bin/python -r /srv/gamst-bench/requirements-mcp.txt']]
        return {'target':'gcp','host':host,'project_id':project,'region':region,'install_requested':install,'side_effects':False,'commands':commands,
                'execution_allowed':False,'reason':'Plan only. VM creation, billing and dataset/model downloads require explicit operator execution on GCP.'}
    def prepare_environment(self,target='local',project_id=None,region='us-central1'):
        plan=self.environment(target,True,project_id,region)
        if target!='local':
            plan['execution_allowed']=False
            return plan
        venv=Path(plan['python']).parent.parent
        if not venv.exists():subprocess.run(plan['commands'][0],check=True,cwd=ROOT)
        subprocess.run(plan['commands'][1],check=True,cwd=ROOT)
        plan['installed']=True
        plan['execution_allowed']=False
        plan['reason']='MCP tooling installed locally; benchmark inference and dataset downloads remain disabled.'
        return plan
    def profiles_info(self):
        return [{'id':k,'benchmark':v.get('benchmark'),'enabled':v.get('enabled',False),'track':v.get('track'),'mode':v.get('mode'),'readiness':self.plan(k)['blockers']} for k,v in self.profiles.items()]

    def plan(self,profile_id,operation='evaluation'):
        require(profile_id in self.profiles,'unknown registered profile')
        p=copy.deepcopy(self.profiles[profile_id]);blockers=[]
        try:validate_profile(p)
        except (ValueError,TypeError,KeyError) as e:blockers.append(str(e))
        if operation=='evaluation' and not re.fullmatch('[a-f0-9]{64}',p.get('dataset_manifest_sha256') or ''):blockers.append('freeze dataset_manifest_sha256 after data preparation')
        if not re.fullmatch('[a-z][a-z0-9-]{4,28}[a-z0-9]',self.config.get('project_id','')):blockers.append('verified GCP project ID missing')
        return {'profile_id':profile_id,'profile_sha256':digest(p),'benchmark':p.get('benchmark'),'track':p.get('track'),
                'metric':p.get('metric'),'split':p.get('split'),'mode':p.get('mode'),'stages':p.get('stages'),
                'blockers':blockers,'ready_to_request_execution':not blockers,'gpu_validated':False,
                'note':'Readiness is structural. GCE, files, permissions, checkpoints and dependencies are checked at execution/review.'}

    def start(self,profile_id,profile_sha256,operation="evaluation"):
        plan=self.plan(profile_id,operation)
        require(not plan['blockers'],'; '.join(plan['blockers']))
        require(plan['profile_sha256']==profile_sha256,'profile changed; request a new plan')
        require(operation in ('evaluation','dataset'),'unknown operation')
        if operation=='dataset':
            require(Path(self.profiles[profile_id].get('hf_executable','')).is_absolute(),'configure absolute hf_executable')
        identity=gce_identity(self.config['project_id']) # before any run directory or child process
        self.root.mkdir(parents=True,exist_ok=True)
        run_id=uuid.uuid4().hex;out=self.root/run_id;out.mkdir()
        p=copy.deepcopy(self.profiles[profile_id])
        frozen={'profile_id':profile_id,'profile':p,'profile_sha256':digest(p),'identity':identity,'project_id':self.config['project_id'],'run_id':run_id,'operation':operation}
        write_new(out/'request.json',frozen)
        with (out/'worker.log').open('xb') as log:
            try:
                subprocess.Popen([sys.executable,'-m','gamst_bench.mcp_worker',str(out)],cwd=ROOT,
                                 stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            except Exception:
                write_new(out/'status.json',{'status':'failed','reason':'worker failed to start'})
                raise
        return {'run_id':run_id,'status':'submitted','profile_sha256':digest(p)}

    def directory(self,run_id):
        require(re.fullmatch('[a-f0-9]{32}',run_id or '') is not None,'invalid run ID')
        p=(self.root/run_id).resolve()
        require(p.parent==self.root and (p/'request.json').is_file(),'unknown run')
        return p

    def list_runs(self):
        if not self.root.exists():return {'runs':[]}
        runs=[]
        for p in sorted(self.root.iterdir(),key=lambda p:p.stat().st_mtime,reverse=True):
            if re.fullmatch('[a-f0-9]{32}',p.name) and p.is_dir() and not p.is_symlink() and (p/'request.json').is_file():
                req=read(p/'request.json')
                runs.append({'run_id':p.name,'profile_id':req.get('profile_id'),'operation':req.get('operation','evaluation'),**self.status(p.name)})
                if len(runs)>=100:break
        return {'runs':runs,'limit':100}

    def status(self,run_id):
        p=self.directory(run_id)
        return read(p/'status.json') if (p/'status.json').exists() else {'status':'submitted','note':'No worker heartbeat yet; not proof of execution.'}

    def cancel(self,run_id):
        p=self.directory(run_id)
        if self.status(run_id).get('status') in ('failed','cancelled','timed_out','execution_finished_review_required','data_downloaded_review_required'):
            return {'status':'already_terminal'}
        (p/'cancel.requested').touch(exist_ok=True)
        return {'status':'cancellation_requested','note':'Worker stops only its owned process group. VM/model servers are unchanged.'}

    def artifacts(self,run_id):
        p=self.directory(run_id);items=[]
        for f in p.rglob('*'):
            if f.is_file() and not f.is_symlink() and f.resolve().is_relative_to(p):
                items.append({'path':str(f.relative_to(p)),'bytes':f.stat().st_size})
                if len(items)>=1000:break
        return {'files':items,'limit':1000}

    def read_artifact(self,run_id,path):
        root=self.directory(run_id);p=(root/path).resolve()
        require(p.is_relative_to(root) and p.is_file() and not Path(path).is_absolute(),'artifact outside run or missing')
        require(p.suffix in ('.json','.jsonl','.log','.txt','.csv'),'text artifacts only')
        # Return a bounded tail. Native logs can contain private data; keep this MCP private.
        with p.open('rb') as f:
            size=p.stat().st_size;f.seek(max(0,size-32768));text=f.read(32768).decode('utf8',errors='replace')
        return {'path':path,'text':text,'truncated':size>32768,'bytes':size}
