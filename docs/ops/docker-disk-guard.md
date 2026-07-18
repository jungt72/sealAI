# Docker disk guard

`ops/docker_disk_guard.py` is the canonical, non-destructive pressure guard for
the Docker data filesystem. It observes one configured mount and emits one
redacted JSON object. It has no Docker client, never invokes a cleanup command,
and never removes images, volumes, caches, backups, logs, or application data.

## Fixed policy

The thresholds are code constants and cannot be overridden by environment or
configuration:

- warning starts at **75%**;
- critical starts at **85%**;
- a critical latch clears only at **80% or below**.

Therefore a filesystem that falls from critical to 81–84% remains
`recovering`. At 75–80% the critical latch is clear, but the ordinary warning
still applies. Only usage below 75% is `healthy`. Release and maintenance gates
use the sustainable recovery target, not the warning boundary: both the fresh
previous sample and current sample must be at or below 80% with the critical
latch clear. Thus 80% is allowed while 81% is blocked, even if an 81–84% sample
has never been critical-latched.

## Commands and exit codes

All normal and error results are single-line JSON. Configured paths and raw
exception text are excluded from output and spool records.

| Command | Behavior | Exit codes |
| --- | --- | --- |
| `check` | Samples usage, applies hysteresis, and (unless dry-run) atomically updates state and the bounded latest-alert record. | `0` healthy, `10` warning, `20` critical/recovering |
| `assert-stable` | Read-only assertion requiring a monitoring sample no older than 15 minutes and a current sample, both at or below 80% and latch-free. | `0` sustainable target met, `21` otherwise |
| `preflight` | Same fail-closed sustainable-target test for release and maintenance entry points. | `0` allowed, `22` blocked |

Operational failures are fail-closed: `64` arguments, `70` unexpected internal
failure, `74` observation/mount failure, `75` lock contention/failure, and `78`
invalid configuration, state, or spool security.

`--dry-run` performs the same observation and decision but does not create or
modify the state directory, state file, alert directory, or alert file. It does
acquire the separate fcntl lock named in the configuration so concurrent runs
cannot disagree.

## Files and permissions

Start from `ops/disk-guard.example.json`. The configured `volume` must be an
active mount point. `state_dir` and its `alerts` child are exactly mode `0700`;
`state.json` and `alerts/latest.json` are atomically written as `0600`. The lock
must be outside the state spool and is held with `fcntl.flock`.

The alert spool is intentionally bounded to `latest.json`: transitions replace
that record instead of growing an unbounded log on an already pressured disk.
Journald retains the same redacted JSON emitted by the service. Exit codes `10`
and `20` are listed in the unit's `SuccessExitStatus`, because warning and
critical are successfully completed observations rather than a broken service.

**External alert delivery status: `BLOCKED_EXTERNAL`.** The local alert spool
and journald are only handoff points. This patch does not prove or configure a
paging, email, webhook, or other off-host delivery path. Until an independently
verified external route exists, operators must not interpret the local record
as notification delivery.

## Install and systemd activation

The installer defaults to a no-write plan:

```bash
ops/install-disk-guard.sh
```

`--apply` runs only from the clean, root-owned, **non-live** detached checkout
created by `ops/bootstrap_gate08_remediation_control.py`. Never execute the
bootstrap, gate, or installer with `sudo` from a user-writable checkout. The
trusted inline loader in `docs/ops/production-release-freeze.md` copies the
bootstrap only as mode-`0600` data to root-private `/run`, verifies those copied
bytes against the fixed private GATE-08 receipt, and makes them executable only
after that match. The verified bootstrap then creates the root-only shallow,
single-branch clone with system Git `--no-local --no-checkout`; the candidate
must advertise the approved commit as `HEAD`. It selects that exact commit
without hooks, tags, or submodules, verifies the full root-only checkout
topology, and hash-verifies the gate and active freeze state before executing
the gate. That verified gate checks every approved artifact and path before the
bootstrap starts the installer. The installer refuses
`/home/thorsten/sealai`, repeats checkout-topology and gate validation, stages
every fixed artifact under a root-private `/run` directory, and re-hashes those
staged bytes against the GATE-08 decision before installing anything. The live
Compose/cron checkout remains unchanged.

It then installs the executable guard and the production storage-lease library,
creates the fixed mode-`0660` `root:thorsten` mutation lock through a
tmpfiles policy, installs/verifies the systemd units, enables the timer, starts
one observation, and verifies the root-owned mode-`0600` state record. It also
requires the configured Docker root to equal `docker info` and to share the
observed filesystem device. The service deliberately has no skip condition: a
missing executable or config makes the scheduled unit fail visibly instead of
silently reporting a skipped check.

The confirmed user-cron entry is destructive and is retired inside the same
approved transaction:

```cron
0 * * * * /home/thorsten/sealai/ops/disk_safeguard.sh
```

Before changing it, the installer requires exactly one matching line, saves the
complete prior crontab as root-private rollback evidence, removes only that
exact line, preserves every other entry, and verifies that no legacy cleanup
process is still running. This neutralization happens before the new files are
activated, so the old hourly `docker builder/image prune` cannot race the
rollout. A failed rollout intentionally never restores destructive automation.

Installing or activating this guard on production is a deployment and remains
subject to a short-lived, root-private GATE-08 remediation-control approval.
That exceptional operation is bound to the exact Git commit and SHA-256 of the
fixed guard artifacts. It exists solely to avoid a bootstrap deadlock while the
normal release freeze remains active; it cannot authorize an application
build, pull, migration, dashboard publish, or storage cleanup. Any image or data
removal remains a separate, evidence-backed GATE-03 action with an explicit
allowlist, backups, batch checks, and approval.

After approved installation, validate without state-spool writes, then create a
monitoring sample before testing the preflight. The preflight remains blocked
until that sample and the current observation both meet the sustainable target:

```bash
/usr/local/libexec/sealai/docker-disk-guard.sh --config /etc/sealai/disk-guard.json --dry-run check
/usr/local/libexec/sealai/docker-disk-guard.sh --config /etc/sealai/disk-guard.json check
/usr/local/libexec/sealai/docker-disk-guard.sh --config /etc/sealai/disk-guard.json preflight
```

The rollout order is mandatory:

1. Make the approved commit available in a local candidate Git repository; its
   checkout may remain user-writable because root never executes its code.
2. Place the exact short-lived GATE-08 receipt at its fixed private path. Its
   exact artifact map includes the bootstrap and active freeze-state file.
3. Use only the independently reviewed inline loader in
   `docs/ops/production-release-freeze.md`. It verifies the bootstrap before
   execution; the bootstrap builds and validates the root-only detached clone,
   then starts the verified installer. Do not run the candidate bootstrap or
   `ops/install-disk-guard.sh` directly through `sudo`.
4. The installer stages/re-hashes inputs, snapshots and retires the one
   destructive cron line, installs controls, enables the timer, and verifies
   the first observation.
5. Verify two later scheduled observations, journald JSON, state/alert modes,
   lock ownership, and timer state. Do not restore the retired cron on failure.

A warning or critical result is an intentional observation signal, never an
instruction to delete anything. External delivery remains
`BLOCKED_EXTERNAL` even after timer activation until separately implemented and
verified.
