"""Audit log service for SEALAI."""

from .event_builder import TrustAuditEvent, TrustAuditEventBuilder

__all__ = ["AuditLogger", "TrustAuditEvent", "TrustAuditEventBuilder"]


def __getattr__(name: str):
    if name == "AuditLogger":
        from .audit_logger import AuditLogger

        return AuditLogger
    raise AttributeError(name)
