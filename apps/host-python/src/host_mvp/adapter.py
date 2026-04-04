from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from .llm_config import apply_env_aliases_for_openharness


class OpenHarnessAdapter:
    def __init__(self) -> None:
        self._repo_root = Path(__file__).resolve().parents[4]
        self._vendor_src = self._repo_root / "vendor" / "OpenHarness" / "src"
        self._loaded = False
        self._module = None
        self._error = None

    def load(self) -> bool:
        if self._loaded:
            return True
        try:
            apply_env_aliases_for_openharness()
            if self._vendor_src.exists():
                src = str(self._vendor_src)
                if src not in sys.path:
                    sys.path.insert(0, src)
            import openharness  # type: ignore

            self._module = openharness
            self._loaded = True
            return True
        except Exception as exc:  # pragma: no cover
            self._error = exc
            self._loaded = False
            return False

    def health(self) -> Dict[str, Any]:
        llm = apply_env_aliases_for_openharness()
        ok = self.load()
        return {
            "ok": ok,
            "vendor_src": str(self._vendor_src),
            "module": getattr(self._module, "__name__", None),
            "error": repr(self._error) if self._error else None,
            "llm": llm,
        }

    def version(self) -> Dict[str, Any]:
        ok = self.load()
        version = getattr(self._module, "__version__", None) if ok else None
        return {
            "ok": ok,
            "openharness_version": version,
        }
