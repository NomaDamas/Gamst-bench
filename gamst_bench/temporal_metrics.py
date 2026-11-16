from __future__ import annotations
import statistics
from dataclasses import dataclass

@dataclass(frozen=True)
class TemporalMetricSummary:
    count: int
    mean_ms: float | None
    p50_ms: float | None
    p95_ms: float | None

def summary(values):
    values=sorted(float(v) for v in values if isinstance(v,(int,float)) and v >= 0)
    if not values: return TemporalMetricSummary(0,None,None,None)
    def percentile(p): return values[min(len(values)-1, max(0, int((len(values)-1)*p + 0.999999)))]
    return TemporalMetricSummary(len(values), statistics.mean(values), percentile(.50), percentile(.95))
def temporal_metrics(records, *, query_cutoff_ms=None, known_evidence=None):
    known=set(known_evidence or ())
    ages=[]; detection=[]; recoveries=[]; cutoff_violations=0; evidence_errors=0; stale_errors=0; drops=0; escalations=0
    for record in records:
        if not isinstance(record,dict): continue
        if isinstance(record.get('age_ms'),(int,float)): ages.append(record['age_ms'])
        if isinstance(record.get('time_to_detect_ms'),(int,float)): detection.append(record['time_to_detect_ms'])
        if isinstance(record.get('recovery_ms'),(int,float)): recoveries.append(record['recovery_ms'])
        if record.get('escalated') is True: escalations += 1
        cutoff_record = record.get('type') in (None, 'answer')
        if query_cutoff_ms is not None and cutoff_record:
            captures=[]
            if isinstance(record.get('capture_timestamp_ms'),int): captures.append(record['capture_timestamp_ms'])
            captures.extend(p.get('capture_timestamp_ms') for p in record.get('evidence_provenance',())
                            if isinstance(p,dict) and isinstance(p.get('capture_timestamp_ms'),int))
            if any(c > query_cutoff_ms for c in captures): cutoff_violations += 1
        ids=record.get('evidence_ids',[])
        if known and any(x not in known for x in ids): evidence_errors += 1
        if record.get('stale_error'): stale_errors += 1
        drops += int(record.get('dropped',0) or 0)
    total = len(records)
    return {'packet_age_ms':summary(ages).__dict__, 'time_to_detect_ms':summary(detection).__dict__,
            'recovery_ms':summary(recoveries).__dict__,
            'query_cutoff_violations':cutoff_violations, 'evidence_id_errors':evidence_errors,
            'stale_state_errors':stale_errors, 'dropped_inputs':drops,
            'recovery_events':sum(1 for r in records if isinstance(r,dict) and r.get('recovered') is True),
            'escalations':escalations, 'escalation_fraction':escalations/total if total else None}
