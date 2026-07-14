# Redis capacity and namespace guard

`ops/redis_capacity_guard.py` is a local control-plane candidate for observing
one exact Redis process. It is deliberately **read-only with respect to Redis**:
its command boundary permits authentication and a small fixed set of metadata,
scan, type, TTL, and cardinality commands. It has no command for `SET`, `DEL`,
`EXPIRE`, eviction-policy changes, ACL changes, scripts, modules, `FLUSH*`, or
any other datastore mutation.

This candidate is not installed or activated by this change. Production
installation is a deployment and requires the separately reviewed GATE-08.
Any TTL, eviction-policy, namespace, or key deletion is a Redis data/config
mutation and remains blocked behind GATE-04. The guard cannot authorize it.

## Fixed decisions

The thresholds are constants, not environment or config inputs:

- the sustainable memory target is **at most 70%** of `maxmemory`;
- 71–74% is `above_target` and 75–79% is `warning`;
- **80% or more is `critical` with decision `deny`**;
- unknown namespaces, unexpected types, TTL-policy violations, category/key or
  queue-depth bound violations, newly observed potential write errors,
  evictions, instance drift, and inconsistent scans also deny.

`maxmemory` must be non-zero and both its exact byte value and
`maxmemory-policy` must match the reviewed config. The example binds
`noeviction`; the guard never changes that policy. TCP is not supported. The
only endpoint is a normalized absolute Unix-socket path. Before `AUTH`, the
guard requires matching Linux `lstat` and `O_PATH`/`fstat` results for a real
socket with the exact configured UID, GID, mode, device, and inode, connects,
checks that the connected descriptor is a socket, repeats the path check, and
on Linux verifies `SO_PEERCRED` against the exact Redis process UID/GID.
Missing peer-credential support,
symlinks, replacement races, or identity drift fail before credential bytes are
sent. This is intentionally not presented as a TLS substitute.

Runtime identity is additionally bound to the SHA-256 of Redis `run_id`, the
replication role, server version, the SHA-256 of a named non-`default` ACL user,
and the canonical ACL contract. A restart changes `run_id` and therefore fails
closed pending a reviewed fingerprint update.

The aggregate JSON event includes used/max memory, key and TTL totals,
evictions and deltas, conservative potential-write-error counters, rejected
connections, queue depth, and per-category ownership/count/type/TTL metrics.
It never includes raw keys, values, prefixes, credentials, exception text,
Redis `run_id`, or usernames. Redis `MEMORY USAGE` is intentionally not summed:
per-key values are not additive allocator truth.

## Namespace configuration

`ops/redis-capacity-guard.example.json` is intentionally non-runnable: its
binding hashes are all zero and are rejected. Create the real file only from a
reviewed, redacted inventory. Every monitored database needs at least one
category and prefixes may not overlap between categories. There is no catch-all
owner: unmatched keys and keys in an unmonitored non-empty database deny.

Each category fixes:

- stable category ID and service owner;
- database and one or more non-secret namespace prefixes;
- expected Redis types;
- TTL policy (`required`, `forbidden`, or `optional`);
- lifecycle kind (`cache`, `checkpoint`, `lock`, `queue`, `session`, `system`);
- maximum key count; and, for queues, maximum per-key depth.

Queue depth is observed only through `LLEN`, `SCARD`, `XLEN`, or `ZCARD`.
Categories using another representation must not be mislabeled as queues.
`maximum_keys` bounds both scan work and the in-memory set of one-way key
digests. If the bound is reached, the guard stops and denies rather than
sampling an incomplete inventory. Code caps it at 300,000 keys and caps each
`SCAN` hint at 2,000. RESP parsing has one shared per-response or per-pipeline
budget: 4 MiB, 12,000 elements, depth three, arrays up to 5,000 elements, bulk
items up to 2 MiB, and at most 4,000 commands per pipeline. Request bytes are
also capped at 4 MiB. Declared-length, nesting, element, or aggregate-budget
poisoning therefore fails closed before unbounded allocation.

## State binding and continuity

State schema v2 stores only aggregates plus a SHA-256 binding fingerprint. Its
canonical input covers every Redis socket/peer/instance/ACL/memory-policy
binding, all fixed thresholds, scan bounds, monitored databases, and every
namespace owner, prefix, type, TTL policy, and category limit. Prefixes enter
the hash but never state or event output.

Counter deltas are calculated only when the current fingerprint equals the
stored fingerprint. A new or changed binding resets deltas and the healthy
sample count. `assert-stable` requires two consecutive healthy observations
with the same fingerprint and a fresh stored sample. Thus a config, namespace,
policy, ACL, process, or instance change cannot inherit an old healthy decision.
Old schema-v1 or malformed state is rejected without overwrite; the rollout
must explicitly archive it inside the approved GATE-08 transaction before the
first v2 sample. There is no implicit migration.

## Credential and ACL dependency

The credential is a mode-`0400` or `0600` JSON object supplied by systemd:

```json
{"username":"named_read_only_guard_user","password":"managed-outside-git"}
```

The proposed unit uses separate encrypted systemd credentials for
`redis-guard-config` and `redis-auth`, exposed only through `%d` to the dedicated
`sealai-redis-guard` service account. The static config therefore does not need
to be writable or owned by that account outside the credential mount.
Provisioning those encrypted inputs, the system user/group, the exact Redis
socket, and a least-privilege Redis ACL is explicitly out of scope here. The
guard fails closed unless `ACL GETUSER` proves the named account is enabled,
password protected, has no selectors or channel patterns, uses exactly the Redis 7
read-key pattern `%R~*`, and has the exact command rules `-@all` plus `PING`,
`ACL WHOAMI`, `ACL GETUSER`, `INFO`, `SELECT`, `DBSIZE`, `SCAN`, `TYPE`, `PTTL`,
and the four queue-cardinality reads. Broader categories, commands, selectors,
key access, or `nopass` are rejected before the first inventory command. The
code-level command boundary independently contains no datastore mutator.

## Commands and outputs

Both commands emit exactly one stable, single-line JSON object. Exit codes are:

| Command/result | Exit |
| --- | ---: |
| healthy `check` | 0 |
| above-target or warning `check` | 10 |
| critical/deny `check` | 20 |
| stable assertion not proven | 21 |
| unexpected internal failure | 70 |
| Redis observation/protocol/binding failure | 74 |
| unsafe or busy lock | 75 |
| unsafe config, credential, state, or spool | 78 |

`check` writes only local aggregate `state.json` and a bounded
`alerts/latest.json`, both mode `0600` below a mode-`0700` state directory.
`--dry-run check` and `assert-stable` do not write those files. All modes remain
read-only against Redis. Memory use is emitted as integer basis points so the
69.99/70/74.99/75/79.99/80 boundaries are evaluated without floating-point or
ceiling ambiguity.

The wrapper starts Bash privileged mode, fixes `PATH`, clears the inherited
environment, and runs isolated system Python. Config, credential, state, alert,
and lock files are opened without following the leaf symlink, with owner/mode
checks and atomic state replacement. The proposed unit runs as the dedicated
`sealai-redis-guard` user, adds only the reviewed Redis socket group, permits
only `AF_UNIX`, has no capabilities, and applies `MemoryHigh=192M`,
`MemoryMax=256M`, and `TasksMax=32`. Running as root is not required; absence of
the dedicated identity or socket group makes activation fail visibly.

## Alerts and rollout boundary

**External alert delivery is `BLOCKED_EXTERNAL`.** Journald and the bounded
local alert record are handoff points only. A separately owned off-host route
must be implemented and tested before operators can rely on notifications.
The proposed systemd unit deliberately treats exit `20` as failure so a deny is
visible even while external delivery is missing; only exit `10` is a completed
warning observation.

Before any approved activation, configure Redis to expose the reviewed Unix
socket, review its UID/GID/mode and every namespace prefix, create the named
read-only ACL and both encrypted credentials, capture fresh binding hashes
without placing raw identifiers in Git, explicitly handle any old state,
verify the service sandbox against the host's systemd version, and exercise a
disposable Redis instance. Do not test this candidate by pointing it at
production from a developer checkout.
