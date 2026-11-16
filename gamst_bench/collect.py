"""Wall-clock causal JSONL collector. Executes only the explicitly provided command."""
import asyncio
import base64
import hashlib
import json
import os
import signal
import time
from pathlib import Path
from .contracts import (PacketIntegrityCounter, canonical, digest, require,
                        validate_plan, verify_packet_checksum, write_new)
from .manifest import manifest_digest, validate_manifest
from .temporal_metrics import temporal_metrics

MAX_LINE = 65536
MAX_OUTPUTS = 10000

def rss_tree(pid):
    """Resident memory of the owned process tree; external model servers excluded."""
    import subprocess
    try:
        lines=subprocess.check_output(['ps','-axo','pid=,ppid=,rss='],text=True,timeout=2).splitlines()
        processes=[tuple(map(int,line.split())) for line in lines]
        selected={pid}
        for _ in range(64):
            children={p for p,parent,_ in processes if parent in selected}
            if children<=selected:break
            selected |= children
        return sum(rss for p,_,rss in processes if p in selected)/1024
    except (OSError,ValueError,subprocess.SubprocessError):return None

async def run_task(plan, system, task, command, *, runtime_manifest_sha256=None):
    started=time.monotonic(); outputs=[]; resources=[]; sent=[]; dropped=0; calls=0
    integrity_counter=PacketIntegrityCounter()
    input_by_id={item['id']:item for item in task['inputs']}
    answer_ready=None; quantities=None; synthetic=False; errors=[]; stderr_bytes=bytearray()
    elapsed=lambda: (time.monotonic()-started)*1000
    proc=await asyncio.create_subprocess_exec(*command,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,limit=MAX_LINE,start_new_session=True)
    pending=asyncio.Queue(maxsize=8)
    stop=asyncio.Event()
    def add_output(message):
        require(len(outputs)<MAX_OUTPUTS,'output cap exceeded')
        outputs.append(message)
    async def write_loop():
        while True:
            message=await pending.get()
            try:
                if message is None:return
                proc.stdin.write(canonical(message)+b'\n');await proc.stdin.drain()
                if message['type']=='input':
                    item=message['input']
                    sent.append({'id':item['id'],'capture_timestamp_ms':item['at_ms'],'sent_ms':elapsed()})
            finally:pending.task_done()
    async def schedule():
        nonlocal dropped
        await pending.put({'type':'start','schema_version':2,'configuration':system,'consumer_model':plan['consumer_model'],'consumer_revision':plan['consumer_revision']})
        events=[(i['at_ms'],0,{'type':'input','input':i}) for i in task['inputs']]
        events.append((task['query_ms'],1,{'type':'query','query':task['query']}))
        for at,_,message in sorted(events,key=lambda e:(e[0],e[1])):
            await asyncio.sleep(max(0,(at-elapsed())/1000))
            if message['type']=='input' and ('blob' in message['input']['payload'] or 'path' in message['input']['payload']):
                item=message['input'];blob=item['payload'].get('blob',item['payload'])
                raw=await asyncio.to_thread(Path(blob['path']).read_bytes)
                require(hashlib.sha256(raw).hexdigest()==blob['sha256'],'media changed after plan freeze')
                require(len(raw)<=4*1024*1024,'media packet exceeds 4 MiB')
                message={'type':'input','input':dict(item,payload={k:v for k,v in item['payload'].items() if k not in ('blob','path','sha256','field')}|{blob['field']:base64.b64encode(raw).decode()})}
            if message['type']=='input' and pending.full():
                dropped+=1;add_output({'type':'drop','received_ms':elapsed(),'input_id':message['input']['id']});continue
            await pending.put(message)
        await asyncio.sleep(max(0,(task['duration_ms']-elapsed())/1000))
        await pending.put({'type':'end'})
        await pending.put(None)
    async def output_loop():
        nonlocal answer_ready,quantities,calls,synthetic
        while True:
            line=await proc.stdout.readline()
            if not line:break
            require(len(line)<=MAX_LINE and line.endswith(b'\n'),'bounded complete JSON line required')
            item=json.loads(line);canonical(item)
            require(type(item) is dict and item.get('type') in ('context','answer','alert','usage','resource','error','meta'), 'invalid adapter output')
            # Optional temporal packets are verified before receiver-side
            # dispatch and before adding the collector receive timestamp.
            if 'packet' in item:
                verify_packet_checksum(item['packet'], counter=integrity_counter)
            item['received_ms']=elapsed() # Never trust provider timestamps for delivery.
            require(item.get('synthetic') is not True or plan['evidence']=='synthetic','synthetic adapter in measured experiment')
            synthetic |= item.get('synthetic') is True
            if item['type'] in ('context','answer','alert'):
                require(type(item.get('text')) is str and len(item['text'])<=32768,'bounded output text required')
                refs=item.get('evidence_ids',[])
                require(type(refs) is list and len(refs)<=128,'bounded evidence required')
                known={v['id'] for v in sent}
                require(set(refs)<=known,'adapter cited evidence not yet delivered')
                item['evidence_provenance']=[dict(id=ref,
                    capture_timestamp_ms=input_by_id[ref]['at_ms'],
                    sent_ms=next(v['sent_ms'] for v in sent if v['id']==ref)) for ref in refs]
            if item['type']=='answer' and answer_ready is None:answer_ready=item['received_ms']
            if item['type']=='usage':
                # Cumulative totals, externally audited before scoring money.
                quantities=item.get('cost_quantities');calls=item.get('calls',calls)
            if item['type']=='resource':
                resources.append({k:item.get(k) for k in ('rss_mb','queue_depth','dropped','age_ms')}|{'at_ms':elapsed(),'scope':'adapter_reported_unverified'})
            if item['type']=='error':errors.append('adapter_error')
            add_output(item)
    async def stderr_loop():
        while chunk:=await proc.stderr.read(1024):
            if len(stderr_bytes)<4096:stderr_bytes.extend(chunk[:4096-len(stderr_bytes)])
    async def profile():
        while not stop.is_set():
            rss=await asyncio.to_thread(rss_tree,proc.pid)
            resources.append({'at_ms':elapsed(),'rss_mb':rss,'queue_depth':pending.qsize(),'dropped':dropped,'age_ms':None,'scope':'owned_process_tree_only'})
            if len(resources)>10000:resources[:]=resources[::2]
            try:await asyncio.wait_for(stop.wait(),timeout=1)
            except asyncio.TimeoutError:pass
    writer=asyncio.create_task(write_loop());schedule_task=asyncio.create_task(schedule());reader=asyncio.create_task(output_loop());err=asyncio.create_task(stderr_loop());profiler=asyncio.create_task(profile())
    status='error'
    async def finish():
        await asyncio.gather(schedule_task,writer,reader,proc.wait())
    try:
        await asyncio.wait_for(finish(),timeout=(task['duration_ms']+plan['timeout_ms'])/1000)
        status='success' if proc.returncode==0 and answer_ready is not None and not errors else 'error'
    except asyncio.TimeoutError:status='timeout'
    except Exception as exc:errors.append(type(exc).__name__)
    finally:
        stop.set()
        # Only the process group created for this invocation is terminated.
        try:
            if proc.returncode is None:os.killpg(proc.pid,signal.SIGKILL)
        except (ProcessLookupError,PermissionError):
            if proc.returncode is None:
                try:proc.kill()
                except ProcessLookupError:pass
        for job in (writer,schedule_task,reader,err,profiler):job.cancel()
        await asyncio.gather(writer,schedule_task,reader,err,profiler,return_exceptions=True)
        await proc.wait()
    trace=dict(plan_sha256=plan['plan_sha256'],input_sha256=task['input_sha256'],task_id=task['id'],system_id=system['id'],
        status=status,clock='wall',synthetic=synthetic or plan['evidence']=='synthetic',answer_ready_ms=answer_ready,
        elapsed_ms=elapsed(),outputs=outputs,resources=resources,sent=sent,dropped_inputs=dropped,cost_quantities=quantities,calls=calls,
        diagnostics=errors,command_sha256=digest(command),stderr_sha256=digest(stderr_bytes.hex()),accounting_status='unverified',
        resource_scope='Owned adapter process tree only. Remote/local model servers and device memory require separate instrumentation.',
        query_cutoff_ms=task['query_ms'], runtime_manifest_sha256=runtime_manifest_sha256,
        integrity_rejected=integrity_counter.integrity_rejected,
        temporal_metrics=temporal_metrics(outputs, query_cutoff_ms=task['query_ms'],
            known_evidence=input_by_id))
    trace['trace_sha256']=digest(trace)
    return trace

async def collect(plan, commands, output, *, runtime_manifest=None):
    validate_plan(plan)
    runtime_manifest_sha256=None
    if plan['evidence']=='measured':
        require(runtime_manifest is not None, 'measured collection requires frozen runtime manifest')
        validate_manifest(runtime_manifest)
        runtime_manifest_sha256=manifest_digest(runtime_manifest)
        require(runtime_manifest_sha256==plan['runtime_manifest_sha256'], 'runtime manifest differs from frozen plan')
    require(set(commands)=={s['id'] for s in plan['systems']},'provide one adapter command per configuration')
    for command in commands.values():
        require(type(command) is list and command and all(type(a) is str and a for a in command),'command must be argv strings')
        require(Path(command[0]).is_absolute(),'adapter executable must be absolute')
    if plan['evidence']=='measured':require(plan['execution_sha256']==digest(commands),'adapter commands differ from frozen plan')
    directory=Path(output);directory.mkdir(parents=True,exist_ok=False)
    write_new(directory/'plan.json',plan)
    write_new(directory/'collection.json',{'status':'started','plan_sha256':plan['plan_sha256'],'commands_sha256':digest(commands),'started_unix':time.time()})
    traces=[]
    for index,task in enumerate(plan['tasks']):
        systems=plan['systems'] if index%2==0 else list(reversed(plan['systems']))
        for system in systems:
            try:
                trace=await run_task(plan,system,task,commands[system['id']],runtime_manifest_sha256=runtime_manifest_sha256)
            except OSError as exc:
                trace=dict(plan_sha256=plan['plan_sha256'],input_sha256=task['input_sha256'],task_id=task['id'],system_id=system['id'],
                    status='error',clock='wall',synthetic=plan['evidence']=='synthetic',answer_ready_ms=None,elapsed_ms=0,
                    outputs=[],resources=[],sent=[],dropped_inputs=0,cost_quantities=None,calls=0,
                    diagnostics=['spawn_failed',type(exc).__name__],command_sha256=digest(commands[system['id']]),accounting_status='unverified',
                    query_cutoff_ms=task['query_ms'],runtime_manifest_sha256=runtime_manifest_sha256,
                    integrity_rejected=0,
                    temporal_metrics=temporal_metrics([],query_cutoff_ms=task['query_ms']))
                trace['trace_sha256']=digest(trace)
            # Ordinal paths avoid interpreting task/config identifiers as file paths.
            write_new(directory/f'trace-{len(traces):05d}.json',trace);traces.append(trace)
    write_new(directory/'traces.json',traces)
    write_new(directory/'complete.json',{'status':'collected_unscored','traces':len(traces),'plan_sha256':plan['plan_sha256']})
    return {'directory':str(directory),'traces':len(traces),'status':'collected_unscored'}
