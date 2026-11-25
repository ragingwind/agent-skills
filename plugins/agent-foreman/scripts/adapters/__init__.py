"""Agent adapters: what agent-foreman does differently per agent kind.

A profile names its agent kind in `agent` (default `claude`). Each kind is a
module that defines the names in `base.REQUIRED`, plus a page in
`<skill>/adapters/<kind>.md` on how to read, answer and exit that agent's
screen. Another kind is one more module listed in ADAPTERS and one more page.
"""
from . import claude, codex
from .base import PLUGIN, REQUIRED, NoTranscript, TokenMissing

ADAPTERS = {claude.KIND: claude, codex.KIND: codex}
KINDS = list(ADAPTERS)
DEFAULT = claude.KIND

__all__ = ["ADAPTERS", "KINDS", "DEFAULT", "PLUGIN", "REQUIRED", "NoTranscript", "TokenMissing", "get", "kind_of"]


def get(kind):
    try:
        return ADAPTERS[kind]
    except KeyError:
        raise ValueError(f"unknown agent kind {kind!r}; known: {', '.join(KINDS)}") from None


def kind_of(profile):
    """The agent kind a profile runs."""
    return profile.get("agent", DEFAULT)
