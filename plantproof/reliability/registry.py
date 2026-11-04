"""Asset registry and examination profiles (Asset Intelligence division).

An asset type is supported only when an examination profile exists for it in
``config/reliability/profiles/<type>.json``. Anything else is reported as unsupported:
pump rules are never applied to other equipment.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain import PROJECT_ROOT

CONFIG_DIR = PROJECT_ROOT / "config" / "reliability"
REGISTRY_PATH = CONFIG_DIR / "assets.json"
PROFILE_DIR = CONFIG_DIR / "profiles"
CRITICALITY = ("Low", "Medium", "High")


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Case:
    case_id: str
    asset_id: str
    source: str              # scenario | fixture
    title: str
    scenario_id: str | None = None
    file: str | None = None


@dataclass(frozen=True)
class Asset:
    asset_id: str
    name: str
    type: str
    location: str | None
    criticality: str | None
    criticality_source: str | None
    specs: tuple[tuple[str, Any], ...]
    cases: tuple[Case, ...]


def _validate_asset(raw: dict[str, Any]) -> Asset:
    for k in ("asset_id", "name", "type", "cases"):
        if not raw.get(k):
            raise RegistryError(f"asset entry missing '{k}': {raw.get('asset_id', '?')}")
    crit = raw.get("criticality")
    if crit is not None and crit not in CRITICALITY:
        raise RegistryError(f"{raw['asset_id']}: criticality must be one of {CRITICALITY} or null")
    cases = []
    for c in raw["cases"]:
        src = c.get("source")
        if src not in ("scenario", "fixture"):
            raise RegistryError(f"{c.get('case_id')}: source must be 'scenario' or 'fixture'")
        if src == "scenario" and not c.get("scenario_id"):
            raise RegistryError(f"{c.get('case_id')}: scenario cases need 'scenario_id'")
        if src == "fixture" and not c.get("file"):
            raise RegistryError(f"{c.get('case_id')}: fixture cases need 'file'")
        cases.append(Case(c["case_id"], raw["asset_id"], src, c.get("title", c["case_id"]),
                          c.get("scenario_id"), c.get("file")))
    return Asset(raw["asset_id"], raw["name"], raw["type"], raw.get("location"), crit,
                 raw.get("criticality_source"), tuple(sorted((raw.get("specs") or {}).items())),
                 tuple(cases))


def load_registry(path: Path = REGISTRY_PATH) -> tuple[Asset, ...]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    assets = tuple(_validate_asset(a) for a in raw.get("assets", []))
    ids = [a.asset_id for a in assets]
    if len(ids) != len(set(ids)):
        raise RegistryError("duplicate asset_id in registry")
    case_ids = [c.case_id for a in assets for c in a.cases]
    if len(case_ids) != len(set(case_ids)):
        raise RegistryError("duplicate case_id in registry")
    return assets


def find_case(case_id: str, assets: tuple[Asset, ...]) -> tuple[Asset, Case]:
    for a in assets:
        for c in a.cases:
            if c.case_id == case_id:
                return a, c
    raise RegistryError(f"unknown case '{case_id}'")


def load_profile(asset_type: str, profile_dir: Path = PROFILE_DIR) -> dict[str, Any] | None:
    """The examination profile for an asset type, or None when the type is unsupported."""
    path = profile_dir / f"{asset_type}.json"
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as fh:
        prof = json.load(fh)
    for k in ("profile_id", "sensors", "condition_bands", "failure_modes"):
        if k not in prof:
            raise RegistryError(f"profile {asset_type} missing '{k}'")
    return prof


def supported_types(profile_dir: Path = PROFILE_DIR) -> tuple[str, ...]:
    return tuple(sorted(p.stem for p in profile_dir.glob("*.json")))


def config_hash(*paths: Path) -> str:
    """Hash of every configuration file a result depends on (for reproducibility)."""
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]
