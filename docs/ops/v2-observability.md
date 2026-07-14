# V2 observability target state

The repository monitoring source of truth is `monitoring/prometheus.yml`,
`monitoring/rules/sealai-v2-alerts.yml`, `monitoring/alertmanager.yml`, and the three provisioned V2
Grafana dashboards. The retired V1 backend job and V1 metric families are rejected by contract
tests. Required V2, worker, host, container, Postgres, Redis, Qdrant, TLS, recovery, and
notification-delivery signals fail closed through explicit missing-signal alerts.

The external TLS contract deliberately uses two Blackbox jobs and two modules. The canonical apex
job requests exactly `https://sealingai.com/api/health` and accepts only HTTP 200. The `www` job
requests exactly `https://www.sealingai.com/api/health` and accepts only HTTP 308 with the exact
`Location: https://sealingai.com/api/health`. Neither module follows redirects. Both require HTTPS,
TLS 1.2 or newer, the system trust chain, and hostname/SAN verification. Separate fail-closed alerts
cover a failed or absent probe for each exact target; certificate-expiry rules cover both jobs. This
prevents the intentional `www` redirect from becoming a permanent false alarm while also preventing
a followed redirect from hiding a broken `www` certificate, hostname, status, or destination.

The configuration uses only aggregate, low-cardinality data. Qdrant scraping reads a dedicated
read-only Docker secret and uses the `api-key` header. Redis and Postgres exporters receive separate
monitoring identities through Docker secrets; they must not reuse application or owner roles.
Prometheus is attached only to the internal observability and metrics networks. Each data exporter
is dual-homed between its one component-specific metrics network and the observability network, so
Prometheus never joins a Postgres or Redis data network. Alertmanager and blackbox-exporter alone
receive narrow egress-only networks for notification delivery and external TLS probes. No
observability service publishes a host port.

LLM and routing counters are updated for every event, independent of metadata-log sampling. No
prompt, response, tenant, case, document, key, URL query, credential, or exception payload becomes a
metric label. Provider cost and quota metrics are supplied by the durable cost-control store; log
parsing is not an accounting source.

The durable outbox worker exposes an internal-only Prometheus listener on port 9101. Each pass
queries aggregate counts from the Postgres authority for the `memory` and `knowledge` queues. It
publishes rows by a fixed status allowlist, oldest unresolved age, unresolved projection backlog,
and an explicit collection-success gauge. A failed query retains the previous state and flips
success to zero; it
never publishes a misleading zero backlog. The backlog is not called "Qdrant drift": only a future
authority-versus-index reconciliation can truthfully produce a drift metric. Provider exception
class names are similarly collapsed
into the fixed categories `timeout`, `rate_limit`, `auth`, `transport`, and `provider`.

The real Compose graph includes Alertmanager, blackbox-exporter, node-exporter, cAdvisor,
postgres-exporter, and redis-exporter. Exporters are read-only, drop all capabilities, use
`no-new-privileges`, and expose only container ports. cAdvisor's minimum host-read mounts and device
access still require target-host runtime verification; privileged mode is not granted. cAdvisor
provides presence, start-time, and OOM signals, but it does not provide Docker healthcheck state.
The rules therefore do not claim a nonexistent `container_health_state` family. Direct Docker
health-state telemetry remains `BLOCKED_EXTERNAL` unless an independently reviewed least-privilege
producer is added; service-level health is covered by fail-closed `up != 1 or absent(up)` alerts.

Every exporter image variable must resolve to an approved digest, the scoped `sealai_monitor`
Postgres/Redis identities must exist, the node textfile directory must exist with reviewed
permissions, and the Prometheus retention size must pass a disk-capacity preflight. Any missing
input blocks GATE-08; Compose must never silently remove a job or alert.

The committed primary and watchdog receivers use only `url_file` and send resolved notifications.
`SealAIWatchdog` fires continuously through Prometheus and Alertmanager at a one-minute cadence. The
watchdog endpoint must be operated outside this VPS and must page when heartbeats stop. That
dead-man control remains `BLOCKED_EXTERNAL` until an owner, expiry policy, and missed-heartbeat test
receipt exist. The isolated verifier
`ops/verify-alert-route.py` replaces that path only inside a private temporary directory, binds both
processes to loopback, injects a synthetic alert, and requires distinct firing and resolution
receipts. It never contacts the configured external endpoint and by itself does not prove the
Prometheus-to-Alertmanager hop.

The node exporter mounts `${NODE_EXPORTER_TEXTFILE_DIR}` read-only at
`/var/lib/node-exporter/textfile`. After the P2-DR work is merged, the gated DR job must render
directly and atomically to `${NODE_EXPORTER_TEXTFILE_DIR}/sealai-dr.prom`, for example with
`ops/dr_recovery.py render-metrics --status ... --output ...`. The rules require all five metric
families for each of `postgres`, `qdrant`, `uploads`, `documents`, and `configuration`; one sample
for a different component cannot mask a missing required component.

Before GATE-08, run the repository contract tests, `promtool check config`, `promtool check rules`,
`amtool check-config`, a complete Compose render, and an isolated alert-route rehearsal. After the
approved deployment, verify every `up` series and both exact Blackbox probe targets, inject each safe
synthetic signal, receive it through the external channel, resolve it, and retain only the redacted
receipt. Do not replace the split probes with a redirect-following check. No production failure is
induced merely to test an alert.

This remediation environment had neither pinned `promtool`, `amtool`, nor `blackbox_exporter`, and
the task prohibited network downloads, daemon use, and remote deployment. Native binary config
loads and the loopback firing/resolution rehearsal are therefore `BLOCKED_EXTERNAL`, not reported as
completed. Repository tests still parse the YAML, inspect semantic fail-closed cases, and render the
actual two-file Compose model without starting containers. GATE-08 must provision
checksum-verified versions that match the pinned Prometheus, Alertmanager, and Blackbox Exporter
images, then run `promtool check config`, `promtool check rules`, `amtool check-config`, a native
Blackbox config load, and the full synthetic Prometheus-to-external-receiver path.
