#!/usr/bin/env python3
"""Convert a captured build log into a redacted, lossless diagnostic report."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from diagnostics.classifier import classify_event, summarize_events

_CANDIDATE = re.compile(
    r"(?:^|\s)(?:fatal error:|error:|warning:)|"
    r"\b(?:FATAL|ERROR|WARNING|WARN):|"
    r"##\[(?:error|warning)\]|"
    r"DeprecationWarning|not found|unsupported|not available|"
    r"Blocking on the main thread|ERR_CANT_CREATE|wait_to_finish",
    re.IGNORECASE,
)


def infer_source(line: str, default_source: str) -> tuple[str, str]:
    lowered = line.lower()
    if "emcc" in lowered or "em++" in lowered or "emscripten" in lowered or "wasm-ld" in lowered:
        return "emscripten", "build_toolchain"
    if "node:" in lowered or "deprecationwarning" in lowered:
        return "node", "build_runtime"
    if "msgfmt" in lowered or "gettext" in lowered:
        return "gettext", "build_dependency"
    if "scons:" in lowered or "scons " in lowered:
        return "scons", "build_orchestrator"
    if re.search(r"(?:fatal error:|error:|warning:|\[-W[^]]+\])", line, re.IGNORECASE):
        return "compiler", "native_compilation"
    return default_source, "build_output"


def ingest_log(input_path: Path, output_path: Path, default_source: str, context: str) -> dict:
    if not input_path.is_file():
        report = {
            "schema_version": 1,
            "health_status": "missing_log",
            "input_file": input_path.name,
            "input_line_count": 0,
            "candidate_count": 0,
            "classification": summarize_events([]),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    raw_lines = input_path.read_text(encoding="utf-8", errors="replace").splitlines()
    events = []
    for line_number, line in enumerate(raw_lines, start=1):
        if not line.strip() or not _CANDIDATE.search(line):
            continue
        source, phase = infer_source(line, default_source)
        lowered = line.lower()
        transport_type = "warning" if ("deprecationwarning" in lowered or "msgfmt not found" in lowered) else "unknown"
        event = classify_event(
            line,
            transport_type=transport_type,
            source_hint=source,
            context=f"{context}:{phase}",
            location=None,
        )
        event["capture_position"] = {
            "file": input_path.name,
            "line": line_number,
        }
        events.append(event)

    summary = summarize_events(events)
    severities = summary["severity_counts"]
    unknown = summary["unknown_events"]
    if severities.get("fatal", 0) or severities.get("error", 0):
        health_status = "degraded"
    elif severities.get("warning", 0) and unknown:
        health_status = "warnings_and_unclassified"
    elif severities.get("warning", 0) and unknown:
        health_status = "warnings_and_unclassified"
    elif severities.get("warning", 0):
        health_status = "warnings"
    elif unknown:
        health_status = "unclassified"
    else:
        health_status = "clean"

    report = {
        "schema_version": 1,
        "health_status": health_status,
        "input_file": input_path.name,
        "input_line_count": len(raw_lines),
        "candidate_count": len(events),
        "classification": summary,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", default="build_log")
    parser.add_argument("--context", default="godot_web_editor_build")
    args = parser.parse_args()
    report = ingest_log(args.input, args.output, args.source, args.context)
    print(json.dumps({
        "health_status": report["health_status"],
        "input_line_count": report["input_line_count"],
        "candidate_count": report["candidate_count"],
        "severity_counts": report["classification"]["severity_counts"],
        "unknown_events": report["classification"]["unknown_events"],
        "report": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
