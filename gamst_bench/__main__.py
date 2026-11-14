import argparse
import asyncio
import json
from pathlib import Path
from .contracts import read,write_new,freeze,validate_plan,digest,require
from .scoring import evaluate
from .fixtures import make_fixture
from .collect import collect

def main():
    parser=argparse.ArgumentParser(description='GAMST context benchmark tools. No model downloads or implicit inference.')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('freeze');p.add_argument('--plan',required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('validate');p.add_argument('--plan',required=True)
    p=sub.add_parser('collect');p.add_argument('--plan',required=True);p.add_argument('--commands',required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('soak');p.add_argument('--plan',required=True);p.add_argument('--commands',required=True);p.add_argument('--system',required=True);p.add_argument('--seconds',type=float,required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('assess-template');p.add_argument('--traces',required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('evaluate');p.add_argument('--plan',required=True);p.add_argument('--traces',required=True);p.add_argument('--assessments',required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('demo');p.add_argument('--out',required=True)
    p=sub.add_parser('import-official');p.add_argument('--report',required=True);p.add_argument('--score',required=True);p.add_argument('--out',required=True)
    args=parser.parse_args()
    if args.command=='freeze':
        result=freeze(read(args.plan));write_new(args.out,result);print(result['plan_sha256'])
    elif args.command=='validate':print(validate_plan(read(args.plan))['plan_sha256'])
    elif args.command=='collect':print(json.dumps(asyncio.run(collect(read(args.plan),read(args.commands),args.out)),indent=2))
    elif args.command=='soak':
        from .soak import soak
        print(json.dumps(asyncio.run(soak(read(args.plan),read(args.commands),args.system,args.seconds,args.out)),indent=2))
    elif args.command=='assess-template':
        rows=[dict(task_id=t['task_id'],system_id=t['system_id'],trace_sha256=t['trace_sha256'],review_status='pending',correct=None,grounded=None,abstained=None,stale_error=None,unsupported_claims=None,claim_count=None,false_alerts=None,correct_facts=[],evidence_ids=[],accounting_complete=False,reviewer='',rubric_revision='',notes='Review source media and trace before scoring.') for t in read(args.traces)]
        write_new(args.out,rows)
    elif args.command=='evaluate':write_new(args.out,evaluate(read(args.plan),read(args.traces),read(args.assessments)))
    elif args.command=='demo':
        destination=Path(args.out);destination.mkdir(parents=True,exist_ok=False)
        plan,traces,assessments,report=make_fixture()
        for name,value in [('plan',plan),('traces',traces),('assessments',assessments),('report',report)]:write_new(destination/(name+'.json'),value)
        print('Synthetic fixtures generated; no model executed; acceptance not established.')
    elif args.command=='import-official':
        from .external import attach_official
        write_new(args.out,attach_official(read(args.report),read(args.score)))

if __name__=='__main__':main()
