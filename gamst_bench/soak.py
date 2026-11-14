"""Long-running lifecycle/resource collection. Never produces quality acceptance."""
import asyncio
import json
import os
import signal
import time
from pathlib import Path
from .collect import rss_tree
from .contracts import validate_plan,require,canonical,digest,write_new

async def soak(plan,commands,system_id,seconds,output):
    validate_plan(plan);require(0<seconds<=28800,'soak duration must be >0 and at most 8h')
    system=next((s for s in plan['systems'] if s['id']==system_id),None);require(system is not None,'unknown system')
    command=commands[system_id]
    if plan['evidence']=='measured':require(plan['execution_sha256']==digest(commands),'frozen command mismatch')
    require(Path(command[0]).is_absolute(),'absolute adapter executable required')
    task=plan['tasks'][0];require(task['inputs'],'soak requires replay inputs')
    require(all('blob' not in i['payload'] for i in task['inputs']),'soak reference uses inline packets; use explicit streaming adapter for external media')
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    write_new(out/'manifest.json',{'plan_sha256':plan['plan_sha256'],'system':system_id,'duration_seconds':seconds,'command_sha256':digest(command),'evidence':plan['evidence'],'scope':'Repeated recorded input, not a real-world accuracy test.'})
    start=time.monotonic();proc=await asyncio.create_subprocess_exec(*command,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=True,limit=65536)
    count=0;errors=0;total=0;profile=[];status='completed';previous='0'*64
    async def send(value):proc.stdin.write(canonical(value)+b'\n');await proc.stdin.drain()
    async def read():
        nonlocal count,errors,total,previous
        with (out/'outputs.jsonl').open('xb') as stream:
            while line:=await proc.stdout.readline():
                total+=len(line);require(total<=128*1024*1024,'soak log exceeds 128 MiB; shorten run or reduce output')
                item=json.loads(line);count+=1;errors+=item.get('type')=='error'
                row={'at_ms':(time.monotonic()-start)*1000,'output':item,'previous_sha256':previous};previous=digest(row)
                stream.write(canonical(dict(row,sha256=previous))+b'\n')
    async def sample():
        while time.monotonic()-start<seconds:
            profile.append({'at_ms':(time.monotonic()-start)*1000,'rss_mb':await asyncio.to_thread(rss_tree,proc.pid)})
            await asyncio.sleep(min(5,seconds))
    async def feed():
        await send({'type':'start','schema_version':2,'configuration':system,'consumer_model':plan['consumer_model'],'consumer_revision':plan['consumer_revision']})
        cycle=0;period=max(task['duration_ms']/1000,.001)
        while time.monotonic()-start<seconds:
            for item in task['inputs']:
                due=cycle*period+item['at_ms']/1000
                if due>=seconds:break
                await asyncio.sleep(max(0,due-(time.monotonic()-start)))
                await send({'type':'input','input':dict(item,id=f"cycle-{cycle}-"+item['id'],at_ms=due*1000)})
            cycle+=1
            await asyncio.sleep(max(0,min(cycle*period,seconds)-(time.monotonic()-start)))
        await send({'type':'end'})
    reader=asyncio.create_task(read());sampler=asyncio.create_task(sample())
    try:
        feeder=asyncio.create_task(feed())
        await asyncio.wait_for(asyncio.gather(feeder,reader),seconds+20)
        await asyncio.wait_for(proc.wait(),5)
        if proc.returncode!=0 or errors:status='adapter_error'
    except Exception as exc:status=type(exc).__name__
    finally:
        try:
            if proc.returncode is None:os.killpg(proc.pid,signal.SIGKILL)
        except (ProcessLookupError,PermissionError):
            if proc.returncode is None:
                try:proc.kill()
                except ProcessLookupError:pass
        reader.cancel();sampler.cancel();feeder.cancel();await asyncio.gather(reader,sampler,feeder,return_exceptions=True);await proc.wait()
    report={'status':status,'evidence':plan['evidence'],'requested_seconds':seconds,'elapsed_seconds':time.monotonic()-start,'outputs':count,'errors':errors,'resources':profile,'last_trace_sha256':previous,'quality_acceptance':False,'scope':'Adapter process-tree RSS only; external model servers/device resources are not included.'}
    write_new(out/'soak.json',report)
    return report
