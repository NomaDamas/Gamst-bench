"""Frozen GAMST benchmark arm descriptors; no inference or metrics are invented here."""
from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class ArmProfile:
    id: str
    name: str
    policy: str
    perception: str
    vlm: str | None
    consumer: str
    measured: bool = False

DEFAULT_ARMS = (
    ArmProfile('B', 'lightweight perception + consumer LLM', 'thin', 'mac-lightweight', None, 'configured-consumer'),
    ArmProfile('C', 'GAMST selective VLM + consumer LLM', 'hybrid', 'mac-lightweight', 'configured-vlm', 'configured-consumer'),
    ArmProfile('D', 'periodic VLM + consumer LLM', 'periodic', 'mac-lightweight', 'configured-vlm', 'configured-consumer'),
    ArmProfile('E', 'small streaming VLM + consumer LLM', 'streaming', 'streaming-vlm', 'configured-streaming-vlm', 'configured-consumer'),
)

def profiles():
    return [asdict(profile) for profile in DEFAULT_ARMS]

def require_measured(profile: ArmProfile):
    if not profile.measured:
        raise RuntimeError(f'benchmark arm {profile.id} has no measured result')
    return profile
