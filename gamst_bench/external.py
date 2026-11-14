"""Attach separately reported official-protocol results with configuration provenance."""
from .contracts import require,number,digest

def attach_official(report,score):
    required=('benchmark','protocol_revision','dataset_revision','scorer_revision','system_id','score','scale','artifact_sha256','source_url','configuration_sha256')
    require(all(k in score for k in required),'official score provenance missing')
    require(score['benchmark'] in ('FastBench','SPOT-Bench','Inf-Streams-Eval','OVO-Bench','OVBench'),'unsupported external benchmark')
    system=next((s for s in report['systems'] if s['id']==score['system_id']),None)
    require(system is not None,'unknown configuration')
    require(score['configuration_sha256']==digest(system),'official score configuration differs')
    for key in ('artifact_sha256','configuration_sha256'):
        require(type(score[key]) is str and len(score[key])==64 and all(c in '0123456789abcdef' for c in score[key]),'SHA256 required')
    require(type(score['source_url']) is str and score['source_url'].startswith('https://'),'HTTPS provenance URL required')
    number(score['scale'],'score scale',1,100);number(score['score'],'official score',0,score['scale'])
    require(score.get('protocol_modified') is False,'modified protocol is not an official-protocol score')
    require(report['evidence']=='measured','cannot attach measured official scores to synthetic demo')
    require(not any(s['benchmark']==score['benchmark'] and s['system_id']==score['system_id'] for s in report['official_scores']),'duplicate official result')
    report['official_scores'].append(score)
    return report
