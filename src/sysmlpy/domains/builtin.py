"""Explicit built-in adapter composition (populated by domain migrations)."""
from .registry import DomainRegistry


def builtin_registry():
    return DomainRegistry()
