"""Lumi v2 tool-layer foundation.

This package is intentionally additive. Existing Help Center/Lumi flows continue to
run unchanged until the orchestrator is explicitly wired in a later phase.
"""

from .context import LumiContext, build_lumi_context
from .orchestrator import LumiOrchestrator
from .tools import build_default_registry

__all__ = [
    "LumiContext",
    "LumiOrchestrator",
    "build_lumi_context",
    "build_default_registry",
]

__version__ = "2.0.0-alpha.1"
