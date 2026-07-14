# V2 logging, redaction, sampling, and retention contract

## Runtime boundary

The standard API and worker log stream is metadata-only. Application messages are static format
strings. Every dynamic logging argument is removed unless a reviewed call site explicitly marks a
short operational code or creates a process-local opaque reference. Opaque references use a random
per-process keyed digest, so small document or case identifiers cannot be enumerated from logs.

The process-wide `Logger.makeRecord` boundary in
`backend/sealai_v2/obs/log_redaction.py` applies after Python has merged `extra` fields and before
API routers and timing logging are configured. It:

- replaces unapproved strings, bytes, collections, and objects with type/length markers;
- removes exception payloads, tracebacks, and stack dumps while retaining the exception class;
- scrubs authorization values, bearer/JWT shapes, common secret assignments, credential-bearing
  connection strings, naked provider-key shapes, URLs with query strings, and structured `extra`
  values as defense in depth;
- rejects free text passed as a purported safe code;
- leaves numeric counters and booleans available for operations.

The pure-ASGI request middleware always generates a new 128-bit correlation ID, ignores an inbound
client ID, returns the server ID as `X-Request-ID`, and keeps its context through streamed response
delivery. The same ID is injected into application logs and timing events. A proxy may log the
upstream response header, but must not copy a client-supplied value into this field.

Paperless ingestion additionally emits only fixed reason codes and opaque document references. It
never logs a document title, source URI, raw exception, extracted text, prompt, or ledger payload.
Client-visible retry failures likewise use fixed codes rather than exception text.

## Sampling

`SEALAI_V2_TELEMETRY_SAMPLE_RATE` controls only high-volume metadata log/trace copies. The accepted
range is `0.0` through `1.0`; invalid values fail closed to zero informational telemetry. An unset
value preserves the current `1.0` behavior for development and tests. The production Compose
profile explicitly defaults the reviewed deployment rate to `0.10` and the production env template
pins it visibly. LLM error events are always emitted and
are never sampled out. Prometheus counters, budget accounting, audit events, security denials, and
backup/restore results must never use this sampler.

## Retention

The production Compose contract must bound every container log with rotation (`max-size` and
`max-file`) and must not use an unbounded local JSON log. Prometheus TSDB retention must be explicit
and capacity-preflighted. Security/audit and cost-accounting records use their dedicated durable
stores and retention policies; they are not reconstructed from sampled Docker logs.

No routine log sink may retain full prompts, responses, uploaded documents, document metadata,
authentication headers, provider payloads, medical content, PII, or connection strings. Temporary
incident diagnostics require a separate human-approved scope, synthetic or pre-redacted data,
owner-only storage, an expiry, and a deletion receipt. Enabling LangSmith
`full_synthetic_only` remains impossible in production.

## Verification and rollout

The Canary suite covers credentials, JWTs, URLs, email/medical-looking content, prompts, document
titles, exception messages, and tracebacks. An AST contract rejects dynamic application logging
messages so arbitrary f-strings cannot bypass argument redaction. Deployment is a GATE-08 action;
production verification must inject synthetic canaries through an isolated test path and then prove
they are absent from every configured log/trace sink without exposing real values.
