# Runtime Credential and Backup Permissions Runbook

The production audit found env/rollback/backup files readable beyond their
intended service owner on a multi-user VPS. This runbook is deliberately not
executed by the repository remediation.

## Safety gate

Obtain an approved maintenance change and an explicit list of paths, owners,
groups, and consuming services. Do not run recursive permission changes across
the repository, Docker data root, or backup volume. A wrong owner/mode can stop
authentication, backup, restore, or certificate renewal.

Inventory only metadata: path, type, mode, owner, group, ACL presence, and
service reference. Never open or print file content. Treat every credential
file that was readable by an unintended account as exposed and rotate it even
after permissions are corrected.

## Target policy

| Artifact | Directory | File | Owner |
|---|---:|---:|---|
| Runtime env/credential file | `0700` | `0600` | exact service/operator account |
| Private key/ACME account material | `0700` | `0600` | exact edge/identity service account |
| Database/Qdrant/Redis backup | `0700` | `0600` | backup operator/service account |
| Sanitized, credential-free schema/example | repository policy | `0644` allowed | repository owner |

Groups and ACLs may be used only when a named multi-service requirement exists;
remove inherited/default ACLs that expand access unintentionally.

## Change procedure

1. Stop new backup/rotation jobs for the shortest approved window or otherwise
   prevent a producer from recreating files during the change.
2. For each **individually approved path**, use metadata-only inspection such
   as `stat`/`getfacl`; do not use `cat`, `grep`, `env`, or recursive content
   tools.
3. Set the approved owner/group, directory mode, and file mode path by path.
   Do not use wildcard examples from a ticket as executable input.
4. Set `umask 077` in the creating backup/rotation process and make scripts
   create temporary/final files with mode `0600` before writing content.
5. Restart/resume only the affected producer/consumer through its sanctioned
   procedure.
6. Verify metadata, service health, backup creation, and a non-destructive
   restore-readiness check. Do not expose payloads during verification.
7. Rotate every credential that may have been read by an unintended local
   account; permission repair is containment, not revocation.

## Acceptance evidence

- approved path inventory has no unintended group/other read bits or ACLs
- producer creates the next artifact with the target mode without post-fix chmod
- named service can read its credential and unrelated login-shell accounts cannot
- backup/renewal/authentication health is green
- affected credentials are rotated/revoked per the rotation runbook
- evidence contains metadata and outcomes only

Rollback may restore an owner/group/mode needed for availability, but must not
restore public/group readability or an exposed credential. If availability and
least privilege conflict, halt and escalate rather than widening access broadly.
