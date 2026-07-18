# Redis P0 emergency review — read-only boundary

This runbook is observation-only. It does not authorize Redis remediation,
configuration changes, key inspection, key deletion, container recreation, or
volume changes.

## Stop thresholds

Stop all planned P0 operational mutation and return
`REDIS_P0_EMERGENCY_REVIEW` when any one condition is observed:

- `used_memory / maxmemory` is at least 0.90, or `maxmemory` cannot be proven;
- any OOM command error is present or increasing;
- any write failure is reported by the application or Redis diagnostics;
- the latest RDB save status is not `ok`;
- AOF is enabled and its last rewrite/write status is not `ok`;
- Redis reports loading, persistence corruption, or an unavailable persistence
  status;
- the container image ID, container identity, mounted volume name, volume
  mountpoint, or Compose project differs from the approved read-only baseline.

Permitted evidence is limited to non-secret container inspection, mounted
volume identity, `INFO memory`, `INFO stats`, and `INFO persistence`. Do not run
commands that enumerate keys or values. Redact connection material from command
transcripts and receipts.

Explicitly forbidden:

- `DEL`, `UNLINK`, `FLUSHDB`, or `FLUSHALL`;
- `CONFIG SET` or any policy/maxmemory change;
- `EVAL` or `EVALSHA`;
- container restart/recreation or volume replacement;
- repair, rewrite, or cleanup commands.

This runbook has no automatic continuation path. The only output after a stop
threshold is:

```text
REDIS_P0_EMERGENCY_REVIEW
```
