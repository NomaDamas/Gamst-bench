"""Frozen runtime manifest validation for reproducible GAMST experiments."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

SCHEMA_VERSION = 1

# A measured runtime manifest must declare the complete temporal provenance
# surface.  These are capability declarations, not measured values: the
# collector still records the concrete timestamps and revisions in each
# trace.  Keeping the declaration in the frozen manifest prevents a run from
# silently omitting a timing dimension that the protocol requires.
REQUIRED_TEMPORAL_FIELDS = frozenset({
    'capture_timestamps',
    'receive_timestamps',
    'process_timestamps',
    'source_clock',
    'clock_drift',
    'av_offset',
    'sequence_gaps',
    'event_intervals',
    'event_revisions',
    'query_cutoffs',
    'freshness',
    'evidence_lineage',
})

def _text(value, name, max_len=4096):
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise ValueError(f'invalid {name}')
    return value

def _sha(value, name):
    value = _text(value, name, 64)
    if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(f'{name} must be lowercase SHA256')
    return value

def _commit_set(value):
    if not isinstance(value, dict) or set(value) != {'gamst', 'gamstcrew', 'gamst-bench'}:
        raise ValueError('repository_commits must contain gamst, gamstcrew and gamst-bench')
    for name, revision in value.items():
        _text(revision, 'repository commit '+name, 40)
        if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
            raise ValueError('repository commit '+name+' must be a lowercase 40-character SHA')
    return value

def repository_commits(value):
    """Validate optional repository provenance.

    Existing synthetic fixtures predate source provenance and may omit this
    field. Measured collection/evaluation enforce its presence explicitly.
    """
    if value is None:
        return None
    return _commit_set(value)

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()

def manifest_digest(manifest):
    return hashlib.sha256(_canonical({k:v for k,v in manifest.items() if k != 'manifest_sha256'})).hexdigest()

def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('manifest schema_version must be 1')
    for key in ('id','runtime_profile','os','arch','hardware','python','consumer_model','consumer_revision','prompt_revision','context_contract'):
        _text(manifest.get(key), key)
    _sha(manifest.get('manifest_sha256'), 'manifest_sha256')
    if manifest['manifest_sha256'] != manifest_digest(manifest):
        raise ValueError('manifest digest mismatch')
    if not isinstance(manifest.get('dependency_lock'), str) or not manifest['dependency_lock']:
        raise ValueError('dependency_lock is required')
    repository_commits(manifest.get('repository_commits'))
    providers = manifest.get('providers')
    if not isinstance(providers, list) or not providers or len(providers) > 128:
        raise ValueError('providers must contain 1..128 entries')
    seen = set()
    for provider in providers:
        if not isinstance(provider, dict): raise ValueError('provider must be an object')
        for key in ('name','revision','model_revision','license'):
            _text(provider.get(key), 'provider '+key)
        if provider['name'] in seen: raise ValueError('duplicate provider')
        seen.add(provider['name'])
        if provider.get('artifact_sha256') is not None: _sha(provider['artifact_sha256'], 'artifact_sha256')
    timing = manifest.get('timing')
    if not isinstance(timing, dict) or timing.get('clock') not in ('monotonic','wall_ms'):
        raise ValueError('timing.clock must be declared')
    for key in ('capture_timestamps','query_cutoffs'):
        if type(timing.get(key)) is not bool: raise ValueError('timing fields must be boolean')
    declared = timing.get('temporal_fields')
    if not isinstance(declared, list) or any(not isinstance(item, str) or not item for item in declared):
        raise ValueError('timing.temporal_fields must be a list')
    if not REQUIRED_TEMPORAL_FIELDS <= set(declared):
        missing = sorted(REQUIRED_TEMPORAL_FIELDS - set(declared))
        raise ValueError('timing.temporal_fields missing: ' + ','.join(missing))
    return manifest

def freeze_manifest(manifest):
    value = dict(manifest); value['schema_version'] = SCHEMA_VERSION; value.pop('manifest_sha256', None)
    value['manifest_sha256'] = manifest_digest(value)
    return validate_manifest(value)

def read_manifest(path):
    payload = Path(path).read_bytes()
    if len(payload) > 1024 * 1024: raise ValueError('manifest exceeds 1 MiB')
    return validate_manifest(json.loads(payload))
