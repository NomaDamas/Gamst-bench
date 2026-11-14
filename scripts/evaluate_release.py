"""Recompute the public report from its declared source artifacts."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gamst_bench.contracts import read
from gamst_bench.scoring import evaluate
manifest=read('data/release.json')
report=evaluate(read(manifest['plan']),read(manifest['traces']),read(manifest['assessments']))
from gamst_bench.external import attach_official
for path in manifest.get('official_scores',[]):
    attach_official(report,read(path))
print(json.dumps(report,ensure_ascii=False,allow_nan=False))
