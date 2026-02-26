from __future__ import annotations

import json
import os
from dataclasses import fields
from pathlib import Path
from typing import Any

from .models import BotConfig


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_value(raw: Any, target: Any) -> Any:
    if raw is None:
        return None
    type_name = str(target)
    if target is bool or "bool" in type_name:
        if isinstance(raw, bool):
            return raw
        return _parse_bool(str(raw))
    if target is int or "int" in type_name:
        return int(raw)
    if target is float or "float" in type_name:
        return float(raw)
    return raw


def load_env_file(env_path: str | Path) -> dict[str, str]:
    path = Path(env_path)
    if not path.exists():
        return {}
    loaded: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        loaded[key.strip()] = value.strip().strip('"').strip("'")
    return loaded


def apply_env_to_process(env_map: dict[str, str]) -> None:
    for key, value in env_map.items():
        os.environ.setdefault(key, value)


def load_json_config(path: str | Path) -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_bot_config(base: dict[str, Any] | None = None, overrides: dict[str, Any] | None = None) -> BotConfig:
    data: dict[str, Any] = {}
    if base:
        data.update(base)
    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})

    valid_fields = {f.name: f for f in fields(BotConfig)}
    normalized: dict[str, Any] = {}

    for key, value in data.items():
        if key not in valid_fields:
            continue
        normalized[key] = _coerce_value(value, valid_fields[key].type)

    if not normalized.get("groq_api_key"):
        normalized["groq_api_key"] = os.getenv("GROQ_API_KEY")
    if not normalized.get("exchange_api_key"):
        normalized["exchange_api_key"] = os.getenv("EXCHANGE_API_KEY")
    if not normalized.get("exchange_api_secret"):
        normalized["exchange_api_secret"] = os.getenv("EXCHANGE_API_SECRET")

    return BotConfig(**normalized)
