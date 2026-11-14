"""Deterministic, lossless classification for heterogeneous build/runtime logs.

Transport severity (for example Chromium's console.error) is deliberately kept
separate from severity declared by the originating tool (for example Godot's
WARNING prefix). Unknown messages are retained and classified as unknown.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any, Iterable

SCHEMA_VERSION = 1
_GODOT_PREFIX = re.compile(r"^\s*(ERROR|WARNING|WARN|INFO|DEBUG|VERBOSE):\s*(.*)$", re.IGNORECASE)
_COMPILER_WARNING = re.compile(r"(?:^|\s)(?:fatal )?warning:|\[-W[^]]+\]", re.IGNORECASE)
_COMPILER_ERROR = re.compile(r"(?:^|\s)(?:fatal )?error:", re.IGNORECASE)


def _fingerprint(source: str, severity: str, message: str, context: str = "") -> str:
    # Source and context are part of identity: equal text from different
    # subsystems is not necessarily the same event or root cause.
    normalized = re.sub(r"\s+", " ", message).strip()
    payload = "\0".join((source, severity, context, normalized))
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
    original = str(message)
    text = original.rstrip("\r\n")
    source = source_hint or "unknown"
    declared_severity = "unknown"
    body = text
    match = _GODOT_PREFIX.match(text)
    if match:
        source = "godot"
        token = match.group(1).upper()
        declared_severity = {
            "ERROR": "error", "WARNING": "warning", "WARN": "warning",
            "INFO": "notice", "DEBUG": "debug", "VERBOSE": "debug",
        }[token]
        body = match.group(2)
    elif _COMPILER_ERROR.search(text):
        source = source if source != "unknown" else "compiler"
        declared_severity = "error"
    elif _COMPILER_WARNING.search(text):
        source = source if source != "unknown" else "compiler"
        declared_severity = "warning"
    elif source == "javascript" and transport_type == "error":
        declared_severity = "error"
    elif source == "javascript" and transport_type == "warning":
        declared_severity = "warning"
    elif transport_type == "warning":
        declared_severity = "warning"
    elif transport_type in {"log", "info"}:
        declared_severity = "notice"
    elif transport_type == "debug":
        declared_severity = "debug"
    elif transport_type == "error":
        declared_severity = "error"

    if source == "unknown":
        lowered_full = text.lower()
        if "emscripten" in lowered_full or "emcc" in lowered_full:
            source = "emscripten"
        elif "github actions" in lowered_full or "##[error]" in lowered_full:
            source = "github_actions"
        elif "node:" in lowered_full or "deprecationwarning" in lowered_full:
            source = "node"

    category = "network" if source in {"network", "http"} else "unknown"
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
        "category": category,
        "context": context,
        "timestamp": timestamp,
        "location": location,
        "classification_status": "classified" if source != "unknown" and declared_severity != "unknown" else "unknown",
    }
    event["fingerprint"] = _fingerprint(source, declared_severity, body, context)
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
