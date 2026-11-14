"""Lossless diagnostics capture and deterministic classification."""

from .classifier import classify_event, link_continuation_events, redact_sensitive_payload, summarize_events

__all__ = ["classify_event", "link_continuation_events", "redact_sensitive_payload", "summarize_events"]
