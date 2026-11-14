"""Synthetic collector test adapter; no inference."""
import json,sys,time
if '--hang' in sys.argv:time.sleep(10)
if '--bad' in sys.argv:print('not JSON',flush=True);sys.exit(0)
refs=[]
for line in sys.stdin:
    item=json.loads(line)
    if item['type']=='input':
        refs.append(item['input']['id'])
        print(json.dumps({'type':'context','text':'fixture observation','evidence_ids':refs[-1:],'synthetic':True}),flush=True)
    elif item['type']=='query':
        print(json.dumps({'type':'answer','text':'fixture answer','evidence_ids':refs[-1:],'synthetic':True}),flush=True)
    elif item['type']=='end':break
