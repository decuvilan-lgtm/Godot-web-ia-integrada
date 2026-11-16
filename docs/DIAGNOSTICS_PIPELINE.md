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
delivers it as a console error. The report retains both facts. Godot `at:` frames and GDScript backtrace formats such as `[0] _ready
(res://main.gd:5)` and `Frame 0 - res://main.gd:6 in function '_ready'` are
structural continuation events, not independent errors. They are linked to a
preceding root event only within a bounded time window and the same diagnostic
context, so editor startup traces cannot attach to project-runtime errors. The known
Emscripten main-thread blocking notice is classified as a warning rather than
inheriting Chromium's transport-level error type. An explicit
Godot prefix has `severity_basis=exact_prefix`; compiler syntax uses
`tool_pattern`; a fallback to transport metadata uses
`transport_fallback`. The basis is visible so reviewers can judge confidence.

## Schema v1 fields

| Field | Meaning |
|---|---|
| `schema_version` | Version of this event contract |
| `original_message` | Captured text after credential/query redaction; all non-sensitive text is preserved |
| `message` | Interpreted message body derived from the safely retained original |
| `source` | Godot engine, Godot script, compiler, JavaScript, network, HTTP, Node, Emscripten, etc. |
| `source_hint` | Source supplied by the capture adapter |
| `source_identification` | exact_prefix, caller_declared, heuristic, or unknown |
| `transport_type` | Original transport-level event type |
| `declared_severity` | fatal, error, warning, notice, debug, or unknown |
| `severity_basis` | Evidence used to assign severity |
| `classification_rule` | Stable rule identifier that explains the deterministic decision |
| `event_role` | Diagnostic root or structural continuation/context |
| `related_event_index` / `relation` | Bounded link from a stack-trace continuation to its preceding root event |
| `godot_source_locations` | GDScript `res://` path and line extracted from a correlated Godot stack frame, when present |
| `redactions_applied` | Number of credential/query redactions applied before persistence |
| `category` | Broad technical nature, not a diagnosis |
| `context` | Workflow phase or subsystem context |
| `timestamp` | Capture timestamp |
| `location` | Available source/browser location metadata |
| `classification_status` | classified or unknown |
| `fingerprint` | Stable grouping key that includes source and location |

Unknown values are valid data. They are not silently discarded and do not get
promoted to warnings or errors without evidence. Credential-like assignments,
Bearer values, and URL query strings are redacted before diagnostic reports
are persisted; `redactions_applied` records message-level changes and
`report_redactions_applied` counts additional recursive redactions across the
complete browser report, including URLs and nested runtime metadata.

## Current browser capture coverage

The Godot Web Chromium smoke test captures:

- all browser console event types (not just console errors);
- uncaught JavaScript page errors;
- failed network requests;
- HTTP responses with status 400 or higher.

It writes the raw diagnostic events and their classified interpretation into
the smoke diagnostics JSON. Existing convenience arrays remain available for
backward compatibility.

The SCons build step also saves its output temporarily, runs the diagnostic ingester, and publishes a redacted build-log report with source line numbers. The temporary unredacted build-log file is removed before artifacts are uploaded. Known gettext fallback messages are treated as warnings; ambiguous messages remain unclassified.

### Project runtime diagnostics

The browser smoke test also opens a dedicated, isolated Godot fixture and runs
its main scene with the editor's Run Current Scene command. The fixture emits
one deliberately identifiable `push_error()` message between
`PROJECT_DIAG_BEGIN` and `PROJECT_DIAG_END` markers. The capture adapter uses
those markers to assign the resulting event and its Godot stack continuation
to `godot_project_runtime`, while editor startup messages remain in
`godot_web_editor_runtime`. The smoke test asserts that exactly one expected
project error is captured and that the GDScript backtrace header and its frame
lines are treated as structural continuations. The expected error is retained
as an error in the artifact, not hidden or downgraded.

This proves the browser capture path can observe at least one real GDScript
runtime error from an executing project and keep its context separate from
editor diagnostics. It does **not** yet claim complete project diagnostics:
static GDScript parse coverage, resource/import failures, scene-load failures,
signals, shader errors, and performance telemetry need dedicated probes and
source-aware correlation. The current project runtime probe is intentionally
small and deterministic. In the Web Project Manager, directory scanning currently
uses a synchronous fallback because browser builds cannot rely on the native
thread path. Very large user-selected directory trees can block the UI; until
scanning is bounded or incremental, prefer ZIP import for large projects.

The classifier is **audit-only**: it does not change engine behavior or suppress
messages. The browser smoke test has a separate functional contract: it checks
that the two project markers occur exactly once and in order, captures exactly
one intentional project runtime error, correlates both expected GDScript source
locations (res://main.gd:5 and res://main.gd:6), verifies the read-only command
rejection, and confirms pending requests return to zero. Diagnostic health
summaries do not independently decide whether the editor build passes.

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
