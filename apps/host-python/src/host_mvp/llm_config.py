from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class LlmConfigView:
    provider: str
    api_format: str
    model: str | None
    base_url_env: str | None
    api_key_env: str | None
    configured: bool


def resolve_llm_config_from_env() -> LlmConfigView:
    deepseek_base = os.environ.get("DEEPSEEK_BASE_URL")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    model = os.environ.get("OPENHARNESS_MODEL") or os.environ.get("ANTHROPIC_MODEL") or os.environ.get("OPENAI_MODEL") or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"

    if deepseek_base and deepseek_key:
        return LlmConfigView(
            provider="deepseek-openai-compatible",
            api_format="openai",
            model=model,
            base_url_env="DEEPSEEK_BASE_URL",
            api_key_env="DEEPSEEK_API_KEY",
            configured=True,
        )

    return LlmConfigView(
        provider="unconfigured",
        api_format="openai",
        model=model,
        base_url_env=None,
        api_key_env=None,
        configured=False,
    )


def apply_env_aliases_for_openharness() -> Dict[str, Any]:
    cfg = resolve_llm_config_from_env()
    changed: Dict[str, Any] = {}
    if cfg.configured:
        os.environ.setdefault("OPENHARNESS_API_FORMAT", "openai")
        os.environ.setdefault("OPENHARNESS_BASE_URL", os.environ["DEEPSEEK_BASE_URL"])
        os.environ.setdefault("OPENAI_API_KEY", os.environ["DEEPSEEK_API_KEY"])
        changed = {
            "OPENHARNESS_API_FORMAT": "openai",
            "OPENHARNESS_BASE_URL": "DEEPSEEK_BASE_URL",
            "OPENAI_API_KEY": "DEEPSEEK_API_KEY",
        }
    return {
        "llm": asdict(cfg),
        "applied_aliases": changed,
    }
