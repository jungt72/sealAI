# P0 operational gate unblock controls

These repository controls prepare narrowly approved operational work. They do
not lift the production release freeze, authorize a deployment, or contain a
production approval manifest.

## GATE-01 same-image credential cutover

`ops/credential_cutover.py` accepts one root-owned `0600` approval at the fixed
private path `/etc/sealai/approvals/gate-01-credential-cutover.json`. The
approval contains service names, immutable fingerprints, and allowed
credential key names, never credential values. Runtime values exist only as
root-owned `0600` files below `/run/sealai/credential-cutover/<service>/`.

The dry-run and apply paths fail closed unless the production commit, clean
checkout, active freeze document, Compose file, Compose project, service,
image ID and digest reference, command, entrypoint, mounts, declared volumes,
networks, ports, restart policy, capabilities, security options, and health
state all match. Apply invokes only `docker compose up` with `--no-deps`,
`--force-recreate`, `--no-build`, and `--pull never`. It never pulls, builds,
migrates, switches checkout, or creates an approval. A post-cutover mismatch
requires owner incident review; the tool does not conceal a partial cutover.
The approval also binds the exact control SHA-256. Apply refuses to run from a
checkout and requires a separately installed root-owned fixed control path.

## GATE-02 object-exact permissions

`ops/permission_manifest.py` supports five separate batches:

- `GATE-02A`: environment and rollback files;
- `GATE-02B`: backup and runtime artifacts;
- `GATE-02C`: key and ACME artifacts before live cutover;
- `GATE-02D`: newly issued live TLS and ACME material.
- `GATE-02E`: explicitly listed existing live TLS and ACME material.

Generation requires an explicit JSON list. There are no globs or directory
walks. Each object is bound to path, type, device, inode, owner, group, mode,
runtime consumers, intended owner/group/mode, and file SHA-256. Symlinks and
non-file/non-directory objects are rejected. Validation opens every object
without following symlinks and rechecks the entire batch before the first
permission mutation. Apply holds the validated file descriptors, writes a
private rollback manifest first, then uses descriptor-bound owner and mode
changes. No production manifest is checked in by this change.
The manifest binds the control SHA-256, and apply likewise refuses to run from
a checkout. Installation of that root-owned fixed control is a separate gate.

GATE-02E does not reinterpret GATE-02D. Every GATE-02E object additionally
binds its lineage, Certbot and Nginx consumer relationship, renewal
configuration path, material kind, and public certificate fingerprint. A
private-key object is opened write-only and is bound only by path, type,
device, inode, owner, group, and mode; its bytes are never read or hashed.
Every lineage must contain an explicitly listed public certificate, private
key, and renewal configuration. Apply writes rollback evidence before the
first descriptor-bound permission change and automatically restores the
complete batch after a partial failure. It never walks a directory, reloads
Nginx, invokes Certbot, or accepts a glob.

## Root-owned operational controls

The separate `operational-control-install` operation is described in
`docs/ops/operational-control-install.md`. It installs only the two GATE-01/
GATE-02 programs and their two schemas at fixed root-owned paths. The GATE-08
approval binds the exact commit, complete artifact set, hashes, target paths,
and pre-existing target fingerprints. It does not authorize any application,
container, release, or systemd action.

## GATE-08 legacy unit retirement

`ops/gate08_legacy_unit_retirement.py` recognizes only
`sealai-docker-disk-guard.timer` and
`sealai-docker-disk-guard.service`. A short-lived root-owned manifest binds
their load state, active state, unit-file state, fixed fragment path, and
fragment SHA-256. The known precondition is an active/enabled legacy timer and
a failed legacy service.

The installer verifies its private staged replacement controls before it asks
the helper to stop and then disable the old timer. It proves that both legacy
PIDs are zero and preserves the old unit bytes plus before/after status as
root-owned private evidence. A later failure deliberately does not reactivate
the potentially destructive timer. After installing the new controls, the
installer proves the old timer inactive/disabled and only the new timer active.

## TLS and ACME subgates

The machine-readable contracts are in `ops/tls-acme-gate-contracts.json`.

1. `GATE-01D0` is read-only. It may correlate only public-key fingerprints,
   certificate serial numbers, lineages, SANs, public JWK thumbprints, and ACME
   account IDs. It must never read or emit private-key bytes.
2. `GATE-01D1` issues entirely new certificates and private keys after D0.
3. `GATE-02D` hardens the new material through the object-exact permission
   engine before it becomes live.
4. `GATE-01D2` performs a separately approved Nginx cutover and public
   endpoint verification.
5. `GATE-01D3` revokes old certificates only after D2 is proven.
6. `GATE-01D4` replaces an ACME account key only when D0 contains concrete
   exposure evidence; uncertainty alone does not authorize it.

Every mutating subgate requires a new owner approval and independent evidence.
This PR implements no certificate issuance, cutover, revocation, or key change.

## Release-freeze boundary

The checked-in release state remains active and `GATE10_LIFT_IMPLEMENTED`
remains false. These controls are preparation for narrow operational approvals,
not an application build, publish, deployment, or general freeze bypass.
