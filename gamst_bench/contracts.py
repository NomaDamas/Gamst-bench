"""Strict, dependency-free validation and content-addressed experiment plans."""
import hashlib
import json
import math
from pathlib import Path

SUITES = {'transient', 'semantic', 'memory', 'revision', 'retention', 'resilience'}
POLICIES = {'vlm', 'thin', 'hybrid', 'periodic', 'no-context', 'oracle'}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def number(value, name, minimum=0, maximum=1e15):
    require(type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum, 'invalid '+name)
    return value

def text(value, name):
    require(type(value) is str and 0 < len(value) <= 4096, 'invalid '+name)
    return value

def integer(value, name, minimum=0, maximum=1000000):
    require(type(value) is int and minimum <= value <= maximum, 'invalid '+name)
    return value

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def read(path):
    payload = Path(path).read_bytes()
    require(len(payload) <= 64*1024*1024, 'input exceeds 64 MiB')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key: '+key)
            result[key] = value
        return result
    result = json.loads(payload, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    canonical(result)
    return result

def write_new(path, value):
    with Path(path).open('xb') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode()+b'\n')

def validate_plan(plan):
    require(plan.get('schema_version') == 2, 'plan schema_version must be 2')
    for key in ('id', 'release', 'protocol', 'consumer_model', 'consumer_revision', 'consumer_prompt_sha256', 'hardware', 'cost_scope'):
        text(plan.get(key), key)
    require(plan.get('evidence') in ('synthetic', 'measured'), 'declare evidence')
    require(type(plan.get('held_out')) is bool, 'declare held_out')
    require(plan.get('split_unit') == 'session', 'split unit must be session')
    require(plan.get('cost_scope') == 'full_pipeline', 'include the whole pipeline')
    integer(plan.get('bootstrap_repetitions'), 'bootstrap repetitions', 500, 5000)
    integer(plan.get('bootstrap_seed'), 'seed', 0, 2**32-1)
    integer(plan.get('min_sessions'), 'minimum sessions', 2, 10000)
    number(plan.get('timeout_ms'), 'timeout', 1, 3600000)
    require(plan.get('failure_latency') == 'timeout', 'failures must remain as timeout penalties')
    require(plan.get('thresholds') == {'cost_ratio': 0.8, 'latency_ratio': 0.9, 'quality_delta': 0}, 'v0.2 gates are fixed; use a new protocol to change them')
    require(type(plan.get('systems')) is list and 2 <= len(plan['systems']) <= 16, 'declare 2..16 configurations')
    ids = set()
    for system in plan['systems']:
        for field in ('id', 'name', 'model', 'revision', 'precision', 'policy', 'sampling', 'window', 'hardware', 'warm_state', 'budget', 'sensor_track'):
            text(system.get(field), 'system '+field)
        require(system['id'] not in ids, 'duplicate configuration')
        ids.add(system['id'])
        require(system['policy'] in POLICIES, 'unknown policy')
        require(system['hardware'] == plan['hardware'], 'hardware mismatch: separate experiment required')
    require(len({s['sensor_track'] for s in plan['systems']}) == 1, 'sensor tracks must match within an experiment')
    semantic_models={(s['model'],s['revision'],s['precision']) for s in plan['systems'] if s['policy'] in ('vlm','hybrid','periodic')}
    require(len(semantic_models)<=1, 'semantic checkpoint and precision must match')
    require(plan.get('baseline') in ids and plan.get('candidate') in ids and plan['baseline'] != plan['candidate'], 'declare distinct baseline / candidate')
    require(type(plan.get('rate_card')) is dict, 'declare rate card, including empty for unknown')
    for key, rate in plan['rate_card'].items():
        text(key, 'rate ID')
        for field in ('unit', 'provider', 'revision', 'category'):
            text(rate.get(field), field)
        number(rate.get('usd_per_unit'), 'price')
    require(type(plan.get('tasks')) is list and 1 <= len(plan['tasks']) <= 10000, 'declare bounded tasks')
    task_ids, sessions = set(), {}
    for task in plan['tasks']:
        for field in ('id', 'session_id', 'participant_id', 'source_id', 'dataset', 'split', 'query', 'sensor_track'):
            text(task.get(field), 'task '+field)
        require(task['sensor_track']==plan['systems'][0]['sensor_track'], 'task sensor track mismatch')
        require(task['suite'] in SUITES and task['split'] in ('dev', 'test'), 'invalid suite / split')
        require(task['id'] not in task_ids, 'duplicate task')
        task_ids.add(task['id'])
        for kind in ('session_id', 'participant_id', 'source_id'):
            key = (kind, task[kind])
            require(key not in sessions or sessions[key] == task['split'], 'split leakage: '+kind)
            sessions[key] = task['split']
        if plan['held_out']:
            require(task['split'] == 'test', 'held-out plan contains development tasks')
        for key in ('duration_ms', 'available_ms', 'query_ms', 'deadline_ms', 'event_duration_ms'):
            number(task.get(key), key)
        require(0 <= task['query_ms'] <= task['duration_ms'] and task['available_ms'] <= task['duration_ms'], 'event/query outside session')
        require(task['duration_ms']+task['deadline_ms'] <= 24*3600000, 'session exceeds one day')
        require(type(task.get('answerable')) is bool, 'declare answerability')
        require(type(task.get('critical_facts')) is list and len(task['critical_facts']) == len(set(task['critical_facts'])), 'unique critical facts required')
        for fact in task['critical_facts']:
            text(fact, 'critical fact')
        inputs = task.get('inputs')
        require(type(inputs) is list and len(inputs) <= 100000, 'bounded input stream required')
        previous, input_ids = -1, set()
        for item in inputs:
            text(item.get('id'), 'input id')
            require(item['id'] not in input_ids, 'duplicate input ID')
            input_ids.add(item['id'])
            number(item.get('at_ms'), 'input time', 0, task['duration_ms'])
            require(item['at_ms'] >= previous, 'inputs must be chronological')
            previous = item['at_ms']
            require(item.get('modality') in ('video', 'audio', 'text', 'control', 'signal'), 'invalid modality')
            require(type(item.get('payload')) is dict, 'payload must be an object')
            if 'blob' in item['payload']:
                blob=item['payload']['blob']
                require(type(blob) is dict and set(blob)=={'path','sha256','field'}, 'exact blob fields required')
                text(blob['path'], 'blob path')
                require(len(blob['sha256'])==64 and all(c in '0123456789abcdef' for c in blob['sha256']), 'blob SHA256 required')
                require(blob['field'] in ('jpeg_base64','pcm_f32_base64'), 'unsupported blob field')
        require(task.get('input_sha256') == digest({'query': task['query'], 'query_ms': task['query_ms'], 'inputs': inputs}), 'task input digest mismatch')
    if plan['evidence'] == 'measured':
        text(plan.get('execution_sha256'), 'frozen adapter commands digest')
        require(len(plan['execution_sha256']) == 64, 'SHA256 required')
    require(plan.get('plan_sha256') == digest({k:v for k,v in plan.items() if k != 'plan_sha256'}), 'plan was changed after freeze')
    return plan

def freeze(plan):
    plan = json.loads(canonical(plan))
    for task in plan['tasks']:
        task['input_sha256'] = digest({'query': task['query'], 'query_ms': task['query_ms'], 'inputs': task['inputs']})
    plan['plan_sha256'] = digest({k:v for k,v in plan.items() if k != 'plan_sha256'})
    return validate_plan(plan)
