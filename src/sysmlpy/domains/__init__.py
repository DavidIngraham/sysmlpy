"""Explicit, context-local domain-library extensions."""
from .registry import (DomainAdapter, DomainContext, DomainDiagnostic, DomainRelation,
                       DomainRegistry, get_registry, using_domains)

__all__ = ["DomainAdapter", "DomainContext", "DomainDiagnostic", "DomainRelation",
           "DomainRegistry", "get_registry", "using_domains"]
