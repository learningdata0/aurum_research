from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Dict
from .config import Settings


SIGNAL_VERSION = "v0.5.0-liquidity-regime"
EXECUTION_VERSION = "v0.5.0-event-driven-1r"


@dataclass(frozen=True)
class ExecutionSignature:
    dataset_hash: str
    parameter_hash: str
    signal_version: str
    execution_version: str

    def short_signature(self) -> str:
        return f"{self.dataset_hash[:8]}:{self.parameter_hash[:8]}:{self.signal_version}:{self.execution_version}"

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def compute_parameter_hash(settings: Settings) -> str:
    """Computes deterministic SHA-256 hash of Settings dataclass."""
    d = asdict(settings)
    # Sort keys for perfect determinism
    s_json = json.dumps(d, sort_keys=True)
    return hashlib.sha256(s_json.encode("utf-8")).hexdigest()


def compute_file_hash(path: str | Path) -> str:
    """Computes deterministic SHA-256 hash of a file on disk."""
    p = Path(path)
    if not p.exists():
        return "FILE_NOT_FOUND"
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_execution_signature(dataset_path: str | Path, settings: Settings) -> ExecutionSignature:
    """
    Creates an immutable execution signature for auditability.
    Guarantees that if any trade count or metric changes, the discrepancy can be
    traced to dataset change, parameter change, signal change, or execution change.
    """
    data_hash = compute_file_hash(dataset_path)
    param_hash = compute_parameter_hash(settings)
    return ExecutionSignature(
        dataset_hash=data_hash,
        parameter_hash=param_hash,
        signal_version=SIGNAL_VERSION,
        execution_version=EXECUTION_VERSION
    )
