from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Mapping, Optional

import yaml

from .runtime import get_runtime_config


@dataclass(frozen=True)
class IntentSpec:
    key: str
    synonyms: tuple[str, ...]
    button_label: Optional[str] = None
    button_tooltip: Optional[str] = None


@dataclass(frozen=True)
class RoutingConfig:
    confidence_threshold: float
    min_delta: float
    intents: Dict[str, IntentSpec]
    fallback_prompt: Optional[str] = None


_DEFAULT_CONF = {
    "confidence_threshold": 0.72,
    "min_delta": 0.08,
    "intents": {
        "werkstoff": {
            "synonyms": ["werkstoff", "material", "ptfe", "hnbr", "elastomer"],
            "button": {"label": "Werkstoff wählen", "tooltip": "Finde den passenden Werkstoff"},
        },
        "profil": {
            "synonyms": ["profil", "bauform", "geometrie", "nutprofil"],
            "button": {"label": "Profil konfigurieren"},
        },
        "validierung": {
            "synonyms": ["validierung", "prüfung", "check", "freigabe"],
            "button": {"label": "Validierung"},
        },
    },
    "fallback": {
        "prompt_template": None,
    },
}


def _load_yaml(path: str) -> Mapping[str, object]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
            if not isinstance(data, Mapping):  # pragma: no cover - defensive guard
                return {}
            return data
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _build_intent_specs(raw: Mapping[str, object]) -> Dict[str, IntentSpec]:
    intents_data = raw.get("intents")
    if not isinstance(intents_data, Mapping):
        intents_data = {}

    intents: Dict[str, IntentSpec] = {}
    for key, value in intents_data.items():
        if not isinstance(value, Mapping):
            continue
        synonyms_raw = value.get("synonyms") or []
        synonyms: List[str] = []
        if isinstance(synonyms_raw, Iterable):
            for item in synonyms_raw:
                if isinstance(item, str) and item.strip():
                    synonyms.append(item.strip().lower())
        button_info = value.get("buttons") or value.get("button") or {}
        label = tooltip = None
        if isinstance(button_info, Mapping):
            label_val = button_info.get("label")
            tooltip_val = button_info.get("tooltip")
            if isinstance(label_val, str) and label_val.strip():
                label = label_val.strip()
            if isinstance(tooltip_val, str) and tooltip_val.strip():
                tooltip = tooltip_val.strip()
        intents[key.lower()] = IntentSpec(
            key=key.lower(),
            synonyms=tuple(dict.fromkeys(synonyms)),
            button_label=label,
            button_tooltip=tooltip,
        )
    return intents


@lru_cache(maxsize=1)
def load_routing_config() -> RoutingConfig:
    runtime_cfg = get_runtime_config()
    raw = _load_yaml(runtime_cfg.routing_conf_path)

    threshold = raw.get("confidence_threshold") if isinstance(raw, Mapping) else None
    min_delta = raw.get("min_delta") if isinstance(raw, Mapping) else None
    fallback = raw.get("fallback") if isinstance(raw, Mapping) else None

    try:
        threshold_val = float(threshold) if threshold is not None else float(_DEFAULT_CONF["confidence_threshold"])  # type: ignore[arg-type]
    except Exception:
        threshold_val = float(_DEFAULT_CONF["confidence_threshold"])  # pragma: no cover - fallback

    try:
        min_delta_val = float(min_delta) if min_delta is not None else float(_DEFAULT_CONF["min_delta"])  # type: ignore[arg-type]
    except Exception:
        min_delta_val = float(_DEFAULT_CONF["min_delta"])  # pragma: no cover - fallback

    fallback_prompt = None
    if isinstance(fallback, Mapping):
        prompt_candidate = fallback.get("prompt_template")
        if isinstance(prompt_candidate, str) and prompt_candidate.strip():
            fallback_prompt = prompt_candidate.strip()

    intents = _build_intent_specs(raw if isinstance(raw, Mapping) else {})
    if not intents:
        intents = _build_intent_specs(_DEFAULT_CONF)

    return RoutingConfig(
        confidence_threshold=threshold_val,
        min_delta=min_delta_val,
        intents=intents,
        fallback_prompt=fallback_prompt,
    )


def routing_available() -> bool:
    cfg = get_runtime_config()
    return cfg.hybrid_routing_enabled and bool(load_routing_config().intents)


__all__ = ["RoutingConfig", "IntentSpec", "load_routing_config", "routing_available"]
