# V2 observability target state

The repository monitoring source of truth is `monitoring/prometheus.yml`,
`monitoring/rules/sealai-v2-alerts.yml`, `monitoring/alertmanager.yml`, and the three provisioned V2
Grafana dashboards. The retired V1 backend job and V1 metric families are rejected by contract
tests. Required V2, worker, host, container, Postgres, Redis, Qdrant, TLS, recovery, and
notification-delivery signals fail closed through explicit missing-signal alerts.

The configuration uses only aggregate, low-cardinality data. Qdrant scraping reads a dedicated
read-only key from a mounted file and uses the `api-key` header. Redis and Postgres exporters must
receive separate monitoring identities via mounted credential files; they must not reuse application
or owner roles. Prometheus, exporters, Alertmanager, and Grafana stay on the internal observability
networks and expose no public host ports.

LLM and routing counters are updated for every event, independent of metadata-log sampling. No
prompt, response, tenant, case, document, key, URL query, credential, or exception payload becomes a
metric label. Provider cost and quota metrics are supplied by the durable cost-control store; log
parsing is not an accounting source.

The durable outbox worker exposes an internal-only Prometheus listener on port 9101. Each pass
queries aggregate counts from the Postgres authority for the `memory` and `knowledge` queues. It
publishes rows by a fixed status allowlist, oldest unresolved age, projection drift, and an explicit
collection-success gauge. A failed query retains the previous state and flips success to zero; it
never publishes a misleading zero backlog. Provider exception class names are similarly collapsed
into the fixed categories `timeout`, `rate_limit`, `auth`, `transport`, and `provider`.

Host and exporter image digests, scoped credentials, Prometheus version compatibility for
file-backed custom HTTP headers, cAdvisor read-only host mounts, capacity/resource limits, and the
external Alertmanager receiver remain deployment inputs. An absent or invalid input blocks GATE-08;
it must never silently remove a scrape job or alert. External notification routing is
`BLOCKED_EXTERNAL` until a human-owned receiver and a synthetic firing/resolution receipt exist.

The committed receiver uses only `url_file` and sends resolved notifications. The isolated verifier
`ops/verify-alert-route.py` replaces that path only inside a private temporary directory, binds both
processes to loopback, injects a synthetic alert, and requires distinct firing and resolution
receipts. It never contacts the configured external endpoint.

Before GATE-08, run the repository contract tests, `promtool check config`, `promtool check rules`,
`amtool check-config`, a complete Compose render, and an isolated alert-route rehearsal. After the
approved deployment, verify every `up` series, inject each safe synthetic signal, receive it through
the external channel, resolve it, and retain only the redacted receipt. No production failure is
induced merely to test an alert.

The local target-state verification used checksum-verified official binaries: Prometheus/promtool
3.10.0, matching the repository's existing Prometheus image digest, and Alertmanager/amtool 0.31.1.
It validated 52 rules, Prometheus configuration syntax, Alertmanager configuration, dashboard JSON,
and one loopback-only firing/resolution rehearsal. Exporter image digests, least-privilege monitoring
identities, production network attachment, resource bounds, a real external receiver, and live
signal injection remain GATE-02/GATE-05/GATE-08 deployment inputs.
