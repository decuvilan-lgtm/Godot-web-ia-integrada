"""Deterministic, lossless classification for heterogeneous build/runtime logs.

Transport severity (for example Chromium's console.error) is deliberately kept
separate from severity declared by the originating tool (for example Godot's
WARNING prefix). Unknown messages are retained and classified as unknown.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any, Iterable

SCHEMA_VERSION = 1
_GODOT_PREFIX = re.compile(r"^\s*(FATAL|CRITICAL|ERROR|WARNING|WARN|INFO|DEBUG|VERBOSE):\s*(.*)$", re.IGNORECASE)
_GODOT_STACK_TRACE = re.compile(r"^\s+at:\s+.*\([^)]*:\d+\)\s*$")
_EMSCRIPTEN_BLOCKING = re.compile(r"Blocking on the main thread is very dangerous", re.IGNORECASE)
_COMPILER_WARNING = re.compile(r"(?:^|\s)(?:fatal )?warning:|\[-W[^]]+\]", re.IGNORECASE)
_COMPILER_FATAL = re.compile(r"(?:^|\s)fatal error:", re.IGNORECASE)
_COMPILER_ERROR = re.compile(r"(?:^|\s)error:", re.IGNORECASE)
_SECRET_ASSIGNMENT = re.compile(r"(?i)(\b(?:access[_-]?token|api[_-]?key|client[_-]?secret|password|passwd|auth[_-]?token|refresh[_-]?token|signature)\s*[=:]\s*)([^\s&,;]+)")
_BEARER_TOKEN = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")
_AUTHORIZATION_HEADER = re.compile(r"(?i)(\bauthorization\s*[=:]\s*)(?:Bearer\s+)?[^\s&,;]+")
_URL_QUERY = re.compile(r"(https?://[^\s?#]+)\?[^\s#]+")


def redact_sensitive_text(value: str) -> tuple[str, int]:
    """Redact credential-like values and URL query strings before reports persist."""
    text = str(value)
    count = 0
    # Redact Bearer credentials before the broader key=value rule so the
    # word "Bearer" cannot be mistaken for the credential value.
    text, n = _AUTHORIZATION_HEADER.subn(lambda match: match.group(1) + "[REDACTED]", text)
    count += n
    text, n = _BEARER_TOKEN.subn(lambda match: match.group(1) + "[REDACTED]", text)
    count += n
    text, n = _SECRET_ASSIGNMENT.subn(lambda match: match.group(1) + "[REDACTED]", text)
    count += n
    text, n = _URL_QUERY.subn(lambda match: match.group(1) + "?[REDACTED_QUERY]", text)
    count += n
    return text, count


def redact_sensitive_payload(value: Any) -> tuple[Any, int]:
    """Recursively redact strings in a report payload before it is persisted."""
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, list):
        safe_items = []
        total = 0
        for item in value:
            safe_item, count = redact_sensitive_payload(item)
            safe_items.append(safe_item)
            total += count
        return safe_items, total
    if isinstance(value, dict):
        safe_mapping = {}
        total = 0
        for key, item in value.items():
            safe_item, count = redact_sensitive_payload(item)
            safe_mapping[key] = safe_item
            total += count
        return safe_mapping, total
    return value, 0


def _fingerprint(source: str, severity: str, message: str, context: str = "", location: dict[str, Any] | None = None) -> str:
    # Source and context are part of identity: equal text from different
    # subsystems is not necessarily the same event or root cause.
    normalized = re.sub(r"\s+", " ", message).strip()
    location_key = json.dumps(location or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload = "\0".join((source, severity, context, location_key, normalized))
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def classify_event(
    message: str,
    *,
    transport_type: str = "unknown",
    source_hint: str = "unknown",
    context: str = "",
    timestamp: str | None = None,
    location: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one event without discarding original text or transport data."""
    captured = str(message)
    original, redactions_applied = redact_sensitive_text(captured)
    text = original.rstrip("\r\n")
    source = source_hint or "unknown"
    declared_severity = "unknown"
    severity_basis = "unknown"
    classification_rule = "fallback.unknown"
    event_role = "diagnostic"
    source_identification = "caller_declared" if source != "unknown" else "unknown"
    body = text
    if _GODOT_STACK_TRACE.match(text):
        source = "godot_stack_trace"
        source_identification = "exact_pattern"
        declared_severity = "notice"
        severity_basis = "structural_pattern"
        classification_rule = "godot.stack_trace.continuation"
        event_role = "continuation"
        body = text.strip()
    elif _EMSCRIPTEN_BLOCKING.search(text):
        source = "emscripten"
        source_identification = "exact_pattern"
        declared_severity = "warning"
        severity_basis = "tool_pattern"
        classification_rule = "emscripten.blocking_main_thread.warning"
    else:
        match = _GODOT_PREFIX.match(text)
    if event_role == "diagnostic" and match:
        source = "godot"
        source_identification = "exact_prefix"
        severity_basis = "exact_prefix"
        token = match.group(1).upper()
        declared_severity = {
            "FATAL": "fatal", "CRITICAL": "fatal", "ERROR": "error",
            "WARNING": "warning", "WARN": "warning", "INFO": "notice",
            "DEBUG": "debug", "VERBOSE": "debug",
        }[token]
        classification_rule = f"godot.prefix.{declared_severity}"
        body = match.group(2)

    elif _COMPILER_FATAL.search(text):
        if source == "unknown":
            source = "compiler"
            source_identification = "heuristic"
        declared_severity = "fatal"
        severity_basis = "tool_pattern"
        classification_rule = "compiler.fatal_error"
    elif _COMPILER_ERROR.search(text):
        if source == "unknown":
            source = "compiler"
            source_identification = "heuristic"
        declared_severity = "error"
        severity_basis = "tool_pattern"
        classification_rule = "compiler.error"
    elif _COMPILER_WARNING.search(text):
        if source == "unknown":
            source = "compiler"
            source_identification = "heuristic"
        declared_severity = "warning"
        severity_basis = "tool_pattern"
        classification_rule = "compiler.warning"
    elif source == "javascript" and transport_type == "error":
        declared_severity = "error"
        severity_basis = "transport_fallback"
        classification_rule = "transport.javascript.error"
    elif source == "javascript" and transport_type == "warning":
        declared_severity = "warning"
        severity_basis = "transport_fallback"
        classification_rule = "transport.javascript.warning"
    elif transport_type == "warning":
        declared_severity = "warning"
        severity_basis = "transport_fallback"
        classification_rule = "transport.warning"
    elif transport_type in {"log", "info"}:
        declared_severity = "notice"
        severity_basis = "transport_fallback"
        classification_rule = "transport.notice"
    elif transport_type == "debug":
        declared_severity = "debug"
        severity_basis = "transport_fallback"
        classification_rule = "transport.debug"
    elif transport_type == "error":
        declared_severity = "error"
        severity_basis = "transport_fallback"
        classification_rule = "transport.error"

    if source == "unknown":
        lowered_full = text.lower()
        if "emscripten" in lowered_full or "emcc" in lowered_full:
            source = "emscripten"
            source_identification = "heuristic"
        elif "github actions" in lowered_full or "##[error]" in lowered_full:
            source = "github_actions"
            source_identification = "heuristic"
        elif "node:" in lowered_full or "deprecationwarning" in lowered_full:
            source = "node"
            source_identification = "heuristic"

    category = "diagnostic_context" if event_role == "continuation" else ("network" if source in {"network", "http"} else "unknown")
    lowered = body.lower()
    category_rules = (
        ("threads", ("thread", "wait_to_finish", "pthread")),
        ("network", ("tcp", "listen", "socket", "https proxy", "websocket")),
        ("memory", ("out of memory", "allocation failed", "memory growth")),
        ("compatibility", ("not available", "unsupported", "unavailable")),
        ("dependencies", ("not found", "missing dependency", "deprecated")),
        ("performance", ("blocking on the main thread", "slow", "performance")),
        ("build_configuration", ("-w", "scons", "compiler flag", "warning: unknown")),
    )
    if event_role != "continuation":
        for candidate, needles in category_rules:
            if any(needle in lowered for needle in needles):
                category = candidate
                break

    event = {
        "schema_version": SCHEMA_VERSION,
        "original_message": original,
        "message": body,
        "source": source,
        "source_hint": source_hint,
        "transport_type": transport_type,
        "declared_severity": declared_severity,
        "severity_basis": severity_basis,
        "classification_rule": classification_rule,
        "event_role": event_role,
        "redactions_applied": redactions_applied,
        "source_identification": source_identification,
        "category": category,
        "context": context,
        "timestamp": timestamp,
        "location": location,
        "classification_status": "classified" if source != "unknown" and declared_severity != "unknown" else "unknown",
    }
    event["fingerprint"] = _fingerprint(source, declared_severity, body, context, location)
    return event


def summarize_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate counts while retaining every event occurrence."""
    materialized = list(events)
    severities = Counter(item.get("declared_severity", "unknown") for item in materialized)
    sources = Counter(item.get("source", "unknown") for item in materialized)
    fingerprints = Counter(item.get("fingerprint", "") for item in materialized)
    return {
        "schema_version": SCHEMA_VERSION,
        "total_events": len(materialized),
        "severity_counts": dict(sorted(severities.items())),
        "source_counts": dict(sorted(sources.items())),
        "unique_fingerprints": len(fingerprints),
        "duplicate_occurrences": sum(count - 1 for count in fingerprints.values() if count > 1),
        "unknown_events": sum(1 for item in materialized if item.get("classification_status") == "unknown"),
        "events": materialized,
    }
