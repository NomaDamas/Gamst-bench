"""Reproducible synthetic protocol scenarios, never a trained-model result."""
from .contracts import freeze,digest
from .scoring import evaluate

NAMES={'transient':'Brief object appearance','semantic':'Small OCR change','memory':'Last seen is not current','revision':'Corrected spoken quantity','retention':'Unannounced retrospective question','resilience':'Disconnect and stale completion'}
TASKS=36
# Illustrative arm profiles. Miss rates and delays are invented to exercise the protocol and dashboard;
# they encode the hypotheses under test, not results. budget_calls = semantic VLM calls per 30 s session.
PRIMARY=[
 dict(id='A',name='VLM-centered',policy='vlm',model='fixture-vlm',budget_calls=30,sampling='VLM every 1 s',miss=.14,delay=1500,jitter=120),
 dict(id='B',name='Thin models only',policy='thin',model='fixture-vlm',budget_calls=0,sampling='thin perception only',miss=.33,delay=280,jitter=100),
 dict(id='C',name='GAMST hybrid',policy='hybrid',model='fixture-vlm',budget_calls=6,sampling='novelty + query triggers, periodic audit'),
 dict(id='D',name='Periodic hybrid',policy='periodic',model='fixture-vlm',budget_calls=6,sampling='fixed-interval VLM'),
 dict(id='E',name='Streaming small VLM',policy='streaming',model='fixture-small-streaming-vlm',budget_calls=120,sampling='small VLM at 4 Hz',miss=.25,delay=420,jitter=80,weak={'semantic','memory'}),
]
SWEEP=[1,2,3,12]
HYBRID_MISS={1:.36,2:.19,3:.11,6:.03,12:.03}
PERIODIC_MISS={1:.53,2:.39,3:.28,6:.17,12:.08}

def arms():
    result=[dict(p,role='primary') for p in PRIMARY]
    for p in result:
        if p['policy']=='hybrid':p.update(miss=HYBRID_MISS[6],delay=700+600//6,jitter=100)
        if p['policy']=='periodic':p.update(miss=PERIODIC_MISS[6],delay=900+3000//6,jitter=100)
    for b in SWEEP:
        result.append(dict(id=f'C{b}',name=f'GAMST hybrid · {b} calls',policy='hybrid',model='fixture-vlm',budget_calls=b,sampling='novelty + query triggers, periodic audit',role='sweep',miss=HYBRID_MISS[b],delay=700+600//b,jitter=100))
        result.append(dict(id=f'D{b}',name=f'Periodic hybrid · {b} calls',policy='periodic',model='fixture-vlm',budget_calls=b,sampling='fixed-interval VLM',role='sweep',miss=PERIODIC_MISS[b],delay=900+3000//b,jitter=100))
    return result

def missed(arm,index,suite):
    # Deterministic spread of misses across tasks; weak suites double the miss rate for that arm.
    rate=min(1,arm['miss']*(2 if suite in arm.get('weak',()) else 1))
    return (index*7+len(arm['id']))%TASKS<round(rate*TASKS)

def make_fixture():
    profiles=arms()
    systems=[dict(id=a['id'],name=a['name'],model=a['model'],revision='fixture-v3',precision='not-applicable',policy=a['policy'],role=a['role'],budget_calls=a['budget_calls'],sampling=a['sampling'],window='past-only, 8 observations',hardware='Synthetic protocol fixture',warm_state='not-applicable',budget=f"{a['budget_calls']} VLM calls / 30 s session",sensor_track='audio+video+text') for a in profiles]
    tasks=[]
    for suite,name in NAMES.items():
        for i in range(6):
            ident=f'{suite}-{i+1:02d}';available=8000+i*500;query=12000 if suite in ('memory','retention') else 1000
            inputs=[{'id':ident+'-start','at_ms':0,'modality':'signal','payload':{'state':'observing','source':'fixture'}}]
            payload={'description':name,'value':str(i+1),'visible':suite!='memory'}
            if suite=='revision':payload={'partial':'three','final':'two','revision_of':'partial-1'}
            if suite=='resilience':payload={'status':'unavailable','generation':2}
            inputs.append({'id':ident+'-event','at_ms':available,'modality':'control' if suite=='resilience' else 'text' if suite in ('semantic','revision') else 'signal','payload':payload})
            tasks.append(dict(id=ident,session_id=ident,participant_id='fixture-person-'+ident,source_id='fixture-source-'+ident,dataset='GAMST Protocol Fixtures',split='test',suite=suite,sensor_track='audio+video+text',query='Report the observable state and cite its evidence: '+name,query_ms=query,available_ms=available,duration_ms=30000,deadline_ms=2000,event_duration_ms=[120,400,1000,2000,5000,10000][i],answerable=not(suite=='resilience' and i==5),critical_facts=[ident+'-fact'],inputs=inputs))
    rate=lambda category,unit,usd:{'unit':unit,'provider':'synthetic','revision':'v3','category':category,'usd_per_unit':usd}
    plan=freeze(dict(schema_version=2,id='gamst-protocol-fixtures-v3',release='2026-11-15',protocol='gamst-context-v0.2',evidence='synthetic',held_out=False,split_unit='session',consumer_model='fixture-consumer',consumer_revision='fixture-v3',consumer_prompt_sha256=digest('fixture'),hardware='Synthetic protocol fixture',cost_scope='full_pipeline',bootstrap_repetitions=500,bootstrap_seed=2026,min_sessions=30,timeout_ms=10000,failure_latency='timeout',baseline='A',candidate='C',controls=['D','E'],thresholds={'cost_ratio':.8,'latency_ratio':.9,'quality_delta':0},
        rate_card={'vlm':rate('vlm','call',.002),'streaming_vlm':rate('vlm','call',.0002),'local':rate('local_compute','session',.001),'consumer':rate('consumer','call',.001)},systems=systems,tasks=tasks))
    tasks=plan['tasks']
    traces=[];assessments=[]
    for arm in profiles:
        sid=arm['id'];streaming=arm['policy']=='streaming'
        for index,task in enumerate(tasks):
            miss=missed(arm,index,task['suite'])
            delay=arm['delay']+(index%6)*arm['jitter']
            anchor=max(task['available_ms'],task['query_ms']); ready=anchor+delay
            refs=[task['inputs'][-1]['id']]
            calls=arm['budget_calls']
            outputs=[{'type':'context','received_ms':anchor+delay*.45,'text':task['inputs'][-1]['payload'].get('description',NAMES[task['suite']]),'evidence_ids':refs},{'type':'answer','received_ms':ready,'text':'Synthetic '+('incorrect' if miss else 'supported')+' answer','evidence_ids':refs}]
            rss=350+(0 if arm['policy']=='thin' else 900 if streaming else min(1250,calls*40+300))
            resources=[{'at_ms':t*5000,'rss_mb':rss+t*2,'queue_depth':int(t%3==0),'dropped':int(arm['policy']=='vlm' and t>3),'age_ms':200+t*80,'scope':'synthetic'} for t in range(7)]
            quantities={'vlm':0 if streaming else calls,'streaming_vlm':calls if streaming else 0,'local':1,'consumer':1}
            trace=dict(plan_sha256=plan['plan_sha256'],input_sha256=task['input_sha256'],task_id=task['id'],system_id=sid,status='success',clock='virtual',synthetic=True,answer_ready_ms=ready,outputs=outputs,resources=resources,cost_quantities=quantities,calls=calls)
            trace['trace_sha256']=digest(trace);traces.append(trace)
            assessments.append(dict(system_id=sid,task_id=task['id'],trace_sha256=trace['trace_sha256'],review_status='synthetic',correct=not miss,grounded=not miss,abstained=not task['answerable'],stale_error=miss and task['suite']=='memory',unsupported_claims=int(miss),claim_count=1,false_alerts=int(miss),correct_facts=[] if miss else task['critical_facts'],evidence_ids=refs,accounting_complete=True))
    return plan,traces,assessments,evaluate(plan,traces,assessments)
