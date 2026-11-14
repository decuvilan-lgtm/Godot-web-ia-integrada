# Diagnostics pipeline (schema v1)

## Purpose

The diagnostics pipeline must preserve what each tool actually emitted before
interpreting it. It must never turn a transport detail into a false statement
about the originating tool, discard unknown messages, or claim a root cause
from a textual match.

## Event flow

1. **Capture:** retain original text, transport type, source hint, timestamp and
   available location/context.
2. **Classify:** infer source and declared severity using deterministic rules.
3. **Group:** calculate a fingerprint using source, severity, context, location
   and normalized message. Grouping is only an aggregate; every occurrence
   remains in the report.
4. **Diagnose:** later stages may correlate events, but correlation is not
   causality. A root cause requires independent evidence and a reproducible
   path.
5. **Validate:** functional assertions are reported separately from log
   classification. A smoke test can pass its functional probes while its
   diagnostic health is degraded; neither result overwrites the other.

## Severity and transport are separate

The schema has two independent fields:

- `transport_type`: how the capture layer delivered the event (for example
  Chromium `error`).
- `declared_severity`: the severity attributed to the originating source.

A Godot message beginning with `WARNING:` remains a warning even if Chromium
delivers it as a console error. The report retains both facts. An explicit
Godot prefix has `severity_basis=exact_prefix`; compiler syntax uses
`tool_pattern`; a fallback to transport metadata uses
`transport_fallback`. The basis is visible so reviewers can judge confidence.

## Schema v1 fields

| Field | Meaning |
|---|---|
| `schema_version` | Version of this event contract |
| `original_message` | Exact text captured before interpretation |
| `message` | Interpreted message body; original remains intact |
| `source` | Godot, compiler, JavaScript, network, HTTP, Node, Emscripten, etc. |
| `source_hint` | Source supplied by the capture adapter |
| `source_identification` | exact_prefix, caller_declared, heuristic, or unknown |
| `transport_type` | Original transport-level event type |
| `declared_severity` | error, warning, notice, debug, or unknown |
| `severity_basis` | Evidence used to assign severity |
| `category` | Broad technical nature, not a diagnosis |
| `context` | Workflow phase or subsystem context |
| `timestamp` | Capture timestamp |
| `location` | Available source/browser location metadata |
| `classification_status` | classified or unknown |
| `fingerprint` | Stable grouping key that includes source and location |

Unknown values are valid data. They are not silently discarded and do not get
promoted to warnings or errors without evidence.

## Current browser capture coverage

The Godot Web Chromium smoke test captures:

- all browser console event types (not just console errors);
- uncaught JavaScript page errors;
- failed network requests;
- HTTP responses with status 400 or higher.

It writes the raw diagnostic events and their classified interpretation into
the smoke diagnostics JSON. Existing convenience arrays remain available for
backward compatibility.

The capture is currently **audit-only**. It does not change engine behavior,
suppress messages, or alter the smoke test's pass/fail policy. CI runs focused
classifier regression tests. A later policy change must be based on measured
baselines and functional impact, not on a desire to make logs look clean.

## Non-goals and safeguards

- A category such as `threads` or `network` does not identify the root cause.
- Similar messages from different sources or source locations must not be
  merged into one identity.
- Duplicate occurrences are counted, never removed from the event list.
- Unknown messages remain visible for review.
- No global warning suppression or automatic source-code patching.
- Do not include secrets or authentication values in diagnostic context.
- Build logs, browser logs, Godot runtime output and functional test results
  remain distinct evidence streams until their provenance can be preserved
  during ingestion.
