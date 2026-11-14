"""Reproducible synthetic protocol scenarios, never a trained-model result."""
from .contracts import freeze,digest
from .scoring import evaluate

NAMES={'transient':'Brief object appearance','semantic':'Small OCR change','memory':'Last seen is not current','revision':'Corrected spoken quantity','retention':'Unannounced retrospective question','resilience':'Disconnect and stale completion'}

def make_fixture():
    systems=[dict(id=key,name=name,model='fixture-perception',revision='fixture-v2',precision='not-applicable',policy=policy,sampling='causal-fixture-events',window='past-only, 8 observations',hardware='Synthetic protocol fixture',warm_state='not-applicable',budget='illustrative 0.10 USD/session',sensor_track='audio+video+text') for key,name,policy in [('A','VLM-centered','vlm'),('B','Thin models only','thin'),('C','GAMST hybrid','hybrid'),('D','Periodic hybrid','periodic')]]
    tasks=[]
    for suite_index,(suite,name) in enumerate(NAMES.items()):
        for i in range(6):
            ident=f'{suite}-{i+1:02d}';available=8000+i*500;query=12000 if suite in ('memory','retention') else 1000
            inputs=[{'id':ident+'-start','at_ms':0,'modality':'signal','payload':{'state':'observing','source':'fixture'}}]
            payload={'description':name,'value':str(i+1),'visible':suite!='memory'}
            if suite=='revision':payload={'partial':'three','final':'two','revision_of':'partial-1'}
            if suite=='resilience':payload={'status':'unavailable','generation':2}
            inputs.append({'id':ident+'-event','at_ms':available,'modality':'control' if suite=='resilience' else 'text' if suite in ('semantic','revision') else 'signal','payload':payload})
            tasks.append(dict(id=ident,session_id=ident,participant_id='fixture-person-'+ident,source_id='fixture-source-'+ident,dataset='GAMST Protocol Fixtures',split='test',suite=suite,sensor_track='audio+video+text',query='Report the observable state and cite its evidence: '+name,query_ms=query,available_ms=available,duration_ms=30000,deadline_ms=2000,event_duration_ms=[120,400,1000,2000,5000,10000][i],answerable=not(suite=='resilience' and i==5),critical_facts=[ident+'-fact'],inputs=inputs))
    plan=freeze(dict(schema_version=2,id='gamst-protocol-fixtures-v2',release='2026-11-14',protocol='gamst-context-v0.2',evidence='synthetic',held_out=False,split_unit='session',consumer_model='fixture-consumer',consumer_revision='fixture-v2',consumer_prompt_sha256=digest('fixture'),hardware='Synthetic protocol fixture',cost_scope='full_pipeline',bootstrap_repetitions=500,bootstrap_seed=2026,min_sessions=30,timeout_ms=10000,failure_latency='timeout',baseline='A',candidate='C',thresholds={'cost_ratio':.8,'latency_ratio':.9,'quality_delta':0},rate_card={'vlm':{'unit':'call','provider':'synthetic','revision':'v2','category':'vlm','usd_per_unit':.002},'local':{'unit':'session','provider':'synthetic','revision':'v2','category':'local_compute','usd_per_unit':.001},'consumer':{'unit':'call','provider':'synthetic','revision':'v2','category':'consumer','usd_per_unit':.001}},systems=systems,tasks=tasks))
    tasks=plan['tasks']
    traces=[];assessments=[]
    for system in systems:
        for index,task in enumerate(tasks):
            sid=system['id'];miss=(sid=='A' and index%7==0) or (sid=='B' and index%3==0) or (sid=='C' and index==2) or (sid=='D' and index%11==0)
            delay={'A':2600,'B':280,'C':750,'D':1450}[sid]+(index%6)*100
            anchor=max(task['available_ms'],task['query_ms']); ready=anchor+delay
            refs=[task['inputs'][-1]['id']]
            calls={'A':12,'B':0,'C':3,'D':6}[sid]
            outputs=[{'type':'context','received_ms':anchor+delay*.45,'text':task['inputs'][-1]['payload'].get('description',NAMES[task['suite']]),'evidence_ids':refs},{'type':'answer','received_ms':ready,'text':'Synthetic '+('incorrect' if miss else 'supported')+' answer','evidence_ids':refs}]
            resources=[{'at_ms':t*5000,'rss_mb':{'A':1600,'B':350,'C':720,'D':900}[sid]+t*2,'queue_depth':int(t%3==0),'dropped':int(sid=='A' and t>3),'age_ms':200+t*80,'scope':'synthetic'} for t in range(7)]
            trace=dict(plan_sha256=plan['plan_sha256'],input_sha256=task['input_sha256'],task_id=task['id'],system_id=sid,status='success',clock='virtual',synthetic=True,answer_ready_ms=ready,outputs=outputs,resources=resources,cost_quantities={'vlm':calls,'local':1,'consumer':1},calls=calls)
            trace['trace_sha256']=digest(trace);traces.append(trace)
            assessments.append(dict(system_id=sid,task_id=task['id'],trace_sha256=trace['trace_sha256'],review_status='synthetic',correct=not miss,grounded=not miss,abstained=not task['answerable'],stale_error=miss and task['suite']=='memory',unsupported_claims=int(miss),claim_count=1,false_alerts=int(miss),correct_facts=[] if miss else task['critical_facts'],evidence_ids=refs,accounting_complete=True))
    return plan,traces,assessments,evaluate(plan,traces,assessments)
