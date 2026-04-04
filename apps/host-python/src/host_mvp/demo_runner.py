from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .llm_config import apply_env_aliases_for_openharness


def _setup_runtime() -> None:
    apply_env_aliases_for_openharness()
    repo_root = Path(__file__).resolve().parents[4]
    config_dir = repo_root / '.tmp' / 'openharness-config'
    data_dir = repo_root / '.tmp' / 'openharness-data'
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('OPENHARNESS_CONFIG_DIR', str(config_dir))
    os.environ.setdefault('OPENHARNESS_DATA_DIR', str(data_dir))
    vendor_src = repo_root / 'vendor' / 'OpenHarness' / 'src'
    if vendor_src.exists():
        src = str(vendor_src)
        if src not in sys.path:
            sys.path.insert(0, src)


async def _collect_events(engine, prompt: str, timeout_sec: int = 90) -> dict[str, Any]:
    text_parts: list[str] = []
    events: list[dict[str, Any]] = []
    tool_sequence: list[str] = []

    async def _run():
        async for event in engine.submit_message(prompt):
            from openharness.engine.stream_events import (
                AssistantTextDelta,
                AssistantTurnComplete,
                ToolExecutionStarted,
                ToolExecutionCompleted,
            )

            e: dict[str, Any] = {}
            if isinstance(event, AssistantTextDelta):
                text_parts.append(event.text)
                e = {'type': 'assistant.delta', 'text': event.text}
            elif isinstance(event, ToolExecutionStarted):
                tool_sequence.append(event.tool_name)
                e = {'type': 'tool.started', 'tool_name': event.tool_name, 'tool_input': event.tool_input}
            elif isinstance(event, ToolExecutionCompleted):
                e = {
                    'type': 'tool.completed',
                    'tool_name': event.tool_name,
                    'is_error': event.is_error,
                    'output_preview': event.output[:600],
                }
            elif isinstance(event, AssistantTurnComplete):
                msg = event.message.model_dump() if hasattr(event.message, 'model_dump') else str(event.message)
                usage = event.usage.model_dump() if hasattr(event.usage, 'model_dump') else str(event.usage)
                e = {'type': 'assistant.complete', 'message': msg, 'usage': usage}
            else:
                kind = event.__class__.__name__
                payload = asdict(event) if is_dataclass(event) else str(event)
                e = {'type': kind, 'payload': payload}

            if e:
                events.append(e)

    try:
        await asyncio.wait_for(_run(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        events.append({'type': 'error.timeout', 'msg': f'validation timed out after {timeout_sec}s'})

    return {
        'tool_sequence': tool_sequence,
        'assistant_text': ''.join(text_parts),
        'events': events,
    }


async def run_single_bash_validation() -> dict[str, Any]:
    """最小真实交互验证：bash pwd"""
    _setup_runtime()
    from openharness.permissions.modes import PermissionMode
    from openharness.config.settings import load_settings, save_settings
    from openharness.ui.runtime import build_runtime, start_runtime, close_runtime

    model = os.environ.get('OPENHARNESS_MODEL') or os.environ.get('DEEPSEEK_MODEL') or 'deepseek-chat'
    settings = load_settings()
    settings.api_format = 'openai'
    settings.model = model
    settings.max_tokens = 4096
    settings.permission.mode = PermissionMode.FULL_AUTO
    save_settings(settings)

    bundle = await build_runtime(api_format='openai', model=model)
    await start_runtime(bundle)
    prompt = "Execute a single tool call: use the `bash` tool to run the command `pwd`. Do not call any other tools."

    try:
        result = await _collect_events(bundle.engine, prompt, timeout_sec=90)
        return {'ok': True, 'scenario': 'bash-pwd', **result}
    except Exception as exc:
        return {'ok': False, 'scenario': 'bash-pwd', 'error_type': exc.__class__.__name__, 'error': str(exc)}
    finally:
        await close_runtime(bundle)


async def run_single_web_search_validation() -> dict[str, Any]:
    """最小真实交互验证：web_search"""
    _setup_runtime()
    from openharness.permissions.modes import PermissionMode
    from openharness.config.settings import load_settings, save_settings
    from openharness.ui.runtime import build_runtime, start_runtime, close_runtime

    model = os.environ.get('OPENHARNESS_MODEL') or os.environ.get('DEEPSEEK_MODEL') or 'deepseek-chat'
    settings = load_settings()
    settings.api_format = 'openai'
    settings.model = model
    settings.max_tokens = 4096
    settings.permission.mode = PermissionMode.FULL_AUTO
    save_settings(settings)

    bundle = await build_runtime(api_format='openai', model=model)
    await start_runtime(bundle)
    prompt = "Execute a single tool call: use the `web_search` tool to search for 'OpenHarness GitHub'."

    try:
        result = await _collect_events(bundle.engine, prompt, timeout_sec=90)
        return {'ok': True, 'scenario': 'web-search', **result}
    except Exception as exc:
        return {'ok': False, 'scenario': 'web-search', 'error_type': exc.__class__.__name__, 'error': str(exc)}
    finally:
        await close_runtime(bundle)


async def run_single_web_fetch_validation() -> dict[str, Any]:
    """最小真实交互验证：web_fetch (target: example.com)"""
    _setup_runtime()
    from openharness.permissions.modes import PermissionMode
    from openharness.config.settings import load_settings, save_settings
    from openharness.ui.runtime import build_runtime, start_runtime, close_runtime

    model = os.environ.get('OPENHARNESS_MODEL') or os.environ.get('DEEPSEEK_MODEL') or 'deepseek-chat'
    settings = load_settings()
    settings.api_format = 'openai'
    settings.model = model
    settings.max_tokens = 4096
    settings.permission.mode = PermissionMode.FULL_AUTO
    save_settings(settings)

    bundle = await build_runtime(api_format='openai', model=model)
    await start_runtime(bundle)
    # 换成更简单的目标地址以避免反爬或网络悬挂
    prompt = "Execute a single tool call: use the `web_fetch` tool to fetch the URL 'https://example.com'."

    try:
        result = await _collect_events(bundle.engine, prompt, timeout_sec=90)
        return {'ok': True, 'scenario': 'web-fetch', **result}
    except Exception as exc:
        return {'ok': False, 'scenario': 'web-fetch', 'error_type': exc.__class__.__name__, 'error': str(exc)}
    finally:
        await close_runtime(bundle)


async def run_combined_tool_validation() -> dict[str, Any]:
    """串联真实交互验证：bash + web_search + web_fetch"""
    _setup_runtime()
    from openharness.permissions.modes import PermissionMode
    from openharness.config.settings import load_settings, save_settings
    from openharness.ui.runtime import build_runtime, start_runtime, close_runtime

    model = os.environ.get('OPENHARNESS_MODEL') or os.environ.get('DEEPSEEK_MODEL') or 'deepseek-chat'
    settings = load_settings()
    settings.api_format = 'openai'
    settings.model = model
    settings.max_tokens = 4096
    settings.permission.mode = PermissionMode.FULL_AUTO
    save_settings(settings)

    bundle = await build_runtime(api_format='openai', model=model)
    await start_runtime(bundle)
    prompt = (
        "You must complete exactly these three steps in order: "
        "1) use bash to run: pwd; "
        "2) use web_search to search: OpenHarness GitHub; "
        "3) use web_fetch to fetch: https://example.com. "
        "After all three tool calls complete, provide a short summary."
    )

    try:
        result = await _collect_events(bundle.engine, prompt, timeout_sec=240)
        return {'ok': True, 'scenario': 'combined', **result}
    except Exception as exc:
        return {'ok': False, 'scenario': 'combined', 'error_type': exc.__class__.__name__, 'error': str(exc)}
    finally:
        await close_runtime(bundle)
