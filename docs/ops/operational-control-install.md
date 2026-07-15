# GATE-08 operational control installation

This control closes only the trust transition from reviewed repository bytes
to four fixed root-owned operational paths. It does not install an application,
lift GATE-10, run a permission batch, rotate a credential, reload Nginx, invoke
Certbot, touch systemd, or recreate a container.

## Fixed approval and operation

The only operation is `operational-control-install`, requiring `GATE-08`. Its
private approval is `/etc/sealai/approvals/gate-08-operational-controls.json`.
The file and every ancestor must be non-symlinked and root-owned; the file mode
must be exactly `0600`. The approval expires no later than four hours after its
approval timestamp and contains no credential values.

The approval binds exactly:

- approval ID and owner;
- the one 40-character source Git commit;
- every path and SHA-256 in the fixed twelve-artifact trust set;
- the four fixed source-to-target mappings;
- `ABSENT`, or the complete root-owned file fingerprint, for every existing
  target.

An existing target fingerprint consists of type, SHA-256, UID, GID, and mode.
Programs must already be `root:root 0755`; schemas must already be
`root:root 0644`. Any extra/missing artifact, target, field, or fingerprint
drift stops before the first target mutation.

## Fixed destinations

```text
/usr/local/libexec/sealai/credential-cutover.py
/usr/local/libexec/sealai/permission-manifest.py
/usr/local/share/sealai/schemas/credential-cutover-approval.schema.json
/usr/local/share/sealai/schemas/permission-manifest.schema.json
```

Directories are `root:root 0755`; programs are `root:root 0755`; schemas are
`root:root 0644`. Both programs independently reject apply execution unless
their real, non-symlinked execution path equals the corresponding fixed path.

## Trust transition and rollback

The bootstrap is first copied as non-executable data by the owner-controlled
loader, compared with the approval hash, made executable, and then invoked as
root. It clones the supplied local repository with fixed Git configuration into
a root-owned `0700` directory below `/run`, verifies the exact commit, rejects
submodules and unsafe paths, and verifies every artifact hash. It then copies
the complete fixed set into a second root-private stage and re-hashes that
stage before executing the GATE-08 decision.

Before installation, all four target preconditions are checked as one batch.
Existing bytes are copied to a private rollback directory below
`/var/lib/sealai-operational-controls/rollbacks`. Each replacement is created
privately in the target directory, assigned its final owner and mode, fsynced,
and atomically renamed. Every installed SHA-256, owner, and mode is checked.
A redacted `0600` receipt is written below
`/var/lib/sealai-operational-controls/receipts`; it contains identifiers and
hashes but no credentials.

A partial error restores every original target or removes a newly introduced
target and verifies the original batch fingerprint. If safe rollback cannot be
proven, exact installed controls are changed to mode `000` and owner incident
review is required. The `/run` checkout and verified stage are always removed;
private rollback evidence remains available.

## Non-mutating preparation

Running `ops/install-operational-controls.sh` without arguments only prints the
planned transaction. Production application requires a fresh exact approval
and an owner-controlled hash-verifying loader. Repository review, tests, or a
merged commit never constitute that approval.
