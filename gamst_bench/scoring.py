"""Externally assessed semantics + instrumented timing; session-paired statistics."""
import math
import random
from decimal import Decimal, localcontext
from .contracts import validate_plan, require, number, integer, digest

def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values)*fraction)-1)] if values else None

def mean(values):
    return sum(values)/len(values) if values else None

def ratio(a, b):
    return a/b if a is not None and b is not None and b > 0 else None

def score_row(plan, task, trace, assessment):
    require(trace['plan_sha256'] == plan['plan_sha256'] and trace['input_sha256'] == task['input_sha256'], 'trace is not from this frozen input')
    unsigned = {k:v for k,v in trace.items() if k != 'trace_sha256'}
    require(trace['trace_sha256'] == digest(unsigned), 'trace digest mismatch')
    require(assessment['trace_sha256'] == trace['trace_sha256'], 'assessment must bind exact trace')
    require(assessment.get('review_status') in ('synthetic', 'reviewed'), 'unreviewed semantic assessment')
    if plan['evidence'] == 'measured':
        require(trace.get('clock') == 'wall' and not trace.get('synthetic', True), 'measured results require wall-clock real collection')
        require(assessment['review_status'] == 'reviewed', 'measured results require independent assessment')
        require(bool(assessment.get('reviewer')) and bool(assessment.get('rubric_revision')), 'reviewer and rubric revision required')
        require(trace.get('command_sha256') is not None, 'execution command provenance required')
    require(trace.get('status') in ('success', 'timeout', 'error'), 'invalid execution status')
    for key in ('correct', 'grounded', 'abstained', 'stale_error'):
        require(type(assessment.get(key)) is bool, 'assessment '+key+' must be boolean')
    integer(assessment.get('unsupported_claims'), 'unsupported claims')
    integer(assessment.get('claim_count'), 'claim count')
    integer(assessment.get('false_alerts'), 'false alerts')
    require(assessment['unsupported_claims'] <= assessment['claim_count'], 'unsupported exceeds claims')
    require(type(assessment.get('correct_facts')) is list and len(set(assessment['correct_facts'])) == len(assessment['correct_facts']), 'duplicate correct facts')
    require(set(assessment['correct_facts']) <= set(task['critical_facts']), 'unknown critical fact')
    require(type(assessment.get('evidence_ids')) is list, 'evidence IDs required')
    outputs = trace.get('outputs', [])
    require(type(outputs) is list, 'outputs must be a list')
    for output in outputs:
        number(output.get('received_ms'), 'output delivery time')
    answers=[o for o in outputs if o.get('type')=='answer']
    require(trace.get('answer_ready_ms') == (answers[0]['received_ms'] if answers else None), 'answer timing must match first final answer')
    delivered = {i['id']:i for i in task['inputs']}
    # Citation existence does not certify semantic support: reviewer explicitly judges it.
    for ref in assessment['evidence_ids']:
        require(ref in delivered, 'nonexistent evidence')
    if plan['evidence']=='measured':
        sent={s['id']:s['sent_ms'] for s in trace.get('sent',[])}
        require(all(ref in sent for ref in assessment['evidence_ids']), 'citation to undelivered input')
    ready = trace.get('answer_ready_ms')
    if ready is not None:
        number(ready, 'answer ready time')
        require(all(delivered[i]['at_ms'] <= ready for i in assessment['evidence_ids']), 'future evidence leakage')
        if plan['evidence']=='measured':require(all(sent[i]<=ready for i in assessment['evidence_ids']), 'answer precedes evidence delivery')
    success = trace['status'] == 'success' and ready is not None
    anchor = max(task['available_ms'], task['query_ms'])
    early = success and ready < anchor
    latency = max(0, ready-anchor) if success and not early else plan['timeout_ms']
    effective_grounded = assessment['grounded'] and assessment['unsupported_claims'] == 0 and (bool(assessment['evidence_ids']) or (not task['answerable'] and assessment['abstained']))
    quality = int(success and not early and assessment['correct'] and effective_grounded and not assessment['stale_error'] and (not assessment['abstained'] or not task['answerable']))
    on_time = bool(quality and latency <= task['deadline_ms'])
    observations = [o for o in outputs if o.get('type') == 'context' and o.get('received_ms', -1) >= task['available_ms']]
    context_ready = next((o['received_ms'] for o in observations if set(assessment['evidence_ids']) <= set(o.get('evidence_ids', [])) and assessment['evidence_ids']), None)
    quantities = trace.get('cost_quantities')
    known_cost = type(quantities) is dict and bool(plan['rate_card']) and set(quantities) == set(plan['rate_card']) and assessment.get('accounting_complete') is True
    cost = None
    exact_cost = None
    vlm_cost = None
    if known_cost and plan['evidence']=='measured':
        require(bool(assessment.get('accounting_evidence')), 'full-pipeline accounting audit evidence required')
    if known_cost:
        for key, quantity in quantities.items(): number(quantity, 'usage '+key)
        with localcontext() as ctx:
            ctx.prec=80
            exact_cost=sum(Decimal(str(quantities[k]))*Decimal(str(v['usd_per_unit'])) for k,v in plan['rate_card'].items())
            cost=float(exact_cost)
        vlm_cost = sum(quantities[k]*v['usd_per_unit'] for k,v in plan['rate_card'].items() if v['category'] == 'vlm')
    for item in trace.get('resources', []):
        for field in ('at_ms','rss_mb','queue_depth','dropped','age_ms'):
            if item.get(field) is not None: number(item[field], field)
    number(trace.get('calls', 0), 'calls')
    return dict(task_id=task['id'], session_id=task['session_id'], system_id=trace['system_id'], suite=task['suite'], dataset=task['dataset'],
        sensor_track=task['sensor_track'], evidence=plan['evidence'], duration_ms=task['duration_ms'], event_duration_ms=task['event_duration_ms'], deadline_ms=task['deadline_ms'],
        available_ms=task['available_ms'], query_ms=task['query_ms'], answer_ready_ms=ready, context_ready_ms=context_ready,
        latency_ms=latency, context_latency_ms=context_ready-task['available_ms'] if context_ready is not None else None,
        success=on_time, quality=quality, status=trace['status'], early=early, correct_facts=len(assessment['correct_facts']) if success and not early else 0, critical_facts=len(task['critical_facts']),
        unsupported_claims=assessment['unsupported_claims'], claim_count=assessment['claim_count'], false_alerts=assessment['false_alerts'],
        abstained=assessment['abstained'], answerable=task['answerable'], stale_error=assessment['stale_error'],
        cost_usd=cost, cost_usd_exact=str(exact_cost) if exact_cost is not None else None, vlm_cost_usd=vlm_cost, calls=trace.get('calls',0), resources=trace.get('resources',[]),
        timeline=[{'type':'evidence','received_ms':task['available_ms'],'label':'Evidence available'}, {'type':'query','received_ms':task['query_ms'],'label':task['query']}] + [{'type':o['type'],'received_ms':o['received_ms'],'label':str(o.get('text',o['type']))[:300]} for o in outputs if o.get('type') in ('context','answer','alert','error')],
        trace_sha256=trace['trace_sha256'])

def summarize(rows):
    hours = sum(r['duration_ms'] for r in rows)/3600000
    cost = sum(r['cost_usd'] for r in rows) if rows and all(r['cost_usd'] is not None for r in rows) else None
    facts = sum(r['critical_facts'] for r in rows)
    claims = sum(r['claim_count'] for r in rows)
    resources = [p for r in rows for p in r['resources']]
    return dict(tasks=len(rows), sessions=len({r['session_id'] for r in rows}), success_rate=mean([int(r['success']) for r in rows]), quality=mean([r['quality'] for r in rows]),
        critical_recall=ratio(sum(r['correct_facts'] for r in rows), facts), unsupported_rate=ratio(sum(r['unsupported_claims'] for r in rows),claims),
        stale_rate=mean([int(r['stale_error']) for r in rows]), false_alerts_per_hour=ratio(sum(r['false_alerts'] for r in rows),hours),
        abstention_rate=mean([int(r['abstained']) for r in rows]), unnecessary_abstentions=sum(r['abstained'] and r['answerable'] for r in rows),
        p50_ms=percentile([r['latency_ms'] for r in rows],.5), p95_ms=percentile([r['latency_ms'] for r in rows],.95),
        context_p95_ms=percentile([r['context_latency_ms'] for r in rows if r['context_latency_ms'] is not None],.95),
        cost_usd=cost, cost_per_hour=ratio(cost,hours), hours=hours, calls=sum(r['calls'] for r in rows),
        peak_rss_mb=max((p['rss_mb'] for p in resources if p.get('rss_mb') is not None),default=None), failures=sum(r['status']!='success' for r in rows))

def comparison(plan, rows, baseline, candidate):
    paired = {s: {r['task_id']:r for r in rows if r['system_id']==s} for s in (baseline,candidate)}
    keys = sorted(paired[baseline])
    require(set(keys)==set(paired[candidate]), 'incomplete paired data')
    clusters = {}
    for key in keys: clusters.setdefault(paired[baseline][key]['session_id'],[]).append(key)
    def metrics(task_ids):
        b,c = [summarize([paired[s][k] for k in task_ids]) for s in (baseline,candidate)]
        with localcontext() as ctx:
            ctx.prec=80
            totals=[sum(Decimal(paired[s][k]['cost_usd_exact']) for k in task_ids) if all(paired[s][k]['cost_usd_exact'] is not None for k in task_ids) else None for s in (baseline,candidate)]
            quality_delta=Decimal(sum(paired[candidate][k]['quality']-paired[baseline][k]['quality'] for k in task_ids))/Decimal(len(task_ids))
            return {'cost_ratio':ratio(totals[1],totals[0]), 'latency_ratio':ratio(Decimal(str(c['p95_ms'])),Decimal(str(b['p95_ms']))), 'quality_delta':quality_delta}
    point=metrics(keys)
    rng=random.Random(plan['bootstrap_seed']); groups=list(clusters.values())
    draws=[metrics([key for group in rng.choices(groups,k=len(groups)) for key in group]) for _ in range(plan['bootstrap_repetitions'])]
    intervals={k: [percentile([d[k] for d in draws],.025),percentile([d[k] for d in draws],.975)] if all(d[k] is not None for d in draws) else None for k in point}
    critical = sum(r['critical_facts'] for r in paired[candidate].values())
    gates=dict(measured=plan['evidence']=='measured', held_out=plan['held_out'], enough_sessions=len(groups)>=plan['min_sessions'],
        critical=critical>0 and all(r['correct_facts']==r['critical_facts'] for r in paired[candidate].values()),
        cost=intervals['cost_ratio'] is not None and point['cost_ratio']<=Decimal('.8') and intervals['cost_ratio'][1]<=Decimal('.8'),
        latency=intervals['latency_ratio'] is not None and point['latency_ratio']<=Decimal('.9') and intervals['latency_ratio'][1]<=Decimal('.9'),
        quality=point['quality_delta']>=0 and intervals['quality_delta'][0]>=0)
    return dict(baseline=baseline,candidate=candidate,point={k:float(v) if v is not None else None for k,v in point.items()},ci95={k:[float(n) for n in v] if v is not None else None for k,v in intervals.items()},exact_point={k:str(v) if v is not None else None for k,v in point.items()},exact_ci95={k:[str(n) for n in v] if v is not None else None for k,v in intervals.items()},gates=gates,status='numeric_pass_requires_audit' if all(gates.values()) else 'not_passed',clusters=len(groups))

def evaluate(plan, traces, assessments):
    validate_plan(plan)
    expected={(s['id'],t['id']) for s in plan['systems'] for t in plan['tasks']}
    lookup={}; grades={}
    for trace in traces:
        key=(trace['system_id'],trace['task_id']);require(key in expected and key not in lookup,'duplicate or unknown trace');lookup[key]=trace
    for assessment in assessments:
        key=(assessment['system_id'],assessment['task_id']);require(key in expected and key not in grades,'duplicate or unknown assessment');grades[key]=assessment
    require(set(lookup)==expected and set(grades)==expected,'missing runs or assessments; failures cannot be omitted')
    rows=[score_row(plan,t,lookup[s['id'],t['id']],grades[s['id'],t['id']]) for s in plan['systems'] for t in plan['tasks']]
    return dict(schema_version=2,release=plan['release'],experiment_id=plan['id'],plan_sha256=plan['plan_sha256'],evidence=plan['evidence'],
        provenance='Synthetic protocol fixtures; no trained model execution.' if plan['evidence']=='synthetic' else 'Measured traces with external assessments; independent audit required.',
        protocol=plan['protocol'],hardware=plan['hardware'],consumer=plan['consumer_model'],systems=plan['systems'],rows=rows,
        summaries={s['id']:summarize([r for r in rows if r['system_id']==s['id']]) for s in plan['systems']},
        comparisons=[comparison(plan,rows,plan['baseline'],plan['candidate'])]+([comparison(plan,rows,'D',plan['candidate'])] if 'D' in {s['id'] for s in plan['systems']} and plan['baseline']!='D' else []),
        official_scores=[],acceptance='not_established' if plan['evidence']=='synthetic' else 'independent_audit_required')
