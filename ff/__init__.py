"""Top-level ff package (flattened layout).

Re-exports key subpackages after repository restructure (removed legacy `python/` prefix).
"""

from importlib import import_module as _imp

_SUBPACKAGES = ["api", "compute", "report", "cli"]

for _name in _SUBPACKAGES:
    try:  # pragma: no cover - defensive import
        _imp(f"ff.{_name}")
    except ImportError:
        pass

__all__ = list(_SUBPACKAGES)
