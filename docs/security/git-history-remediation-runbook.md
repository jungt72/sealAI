# Git History Credential Remediation Runbook

Removing a credential from the current tree prevents new checkouts from seeing
it at `HEAD`; it does not remove old Git objects, forks, caches, CI artifacts, or
existing clones. Rotation/revocation is therefore mandatory before history
rewriting.

This is a destructive shared-repository operation. It requires explicit owner
approval naming the repository, refs/tags in scope, maintenance window, force
update, clone/fork communication, and rollback/archive policy. Do not execute it
as part of an ordinary remediation PR.

## Preconditions

- every affected credential is replaced and the old credential is revoked
- the current default-branch tree and secret-scan CI are clean
- branch protection/required checks and deployment freeze are coordinated
- open PRs, tags, release refs, submodules, mirrors, and forks are inventoried
- an access-controlled, encrypted pre-rewrite mirror is approved for legal or
  incident retention; it is itself classified as containing compromised data
- an approved history-rewrite tool and exact path/object inventory are peer
  reviewed

The confirmed path inventory starts with:

```text
certs/tls.key
keycloak/certs/key.pem
nginx/certbot/accounts/
docs/debug_internal_error/20251222T100929Z/
docs/debug_internal_error/live/
```

The directory paths intentionally include the additional raw diagnostic and
ACME registration metadata removed during remediation. Resolve exact historical
paths from Git metadata without printing blob content.

## Rewrite plan

1. Freeze merges, pushes, releases, and automated mirrors.
2. Create the controlled mirror/archive and record its custody.
3. Run the approved path-based rewrite against all explicitly approved branches
   and tags. Never use a value-based search that puts a credential into command
   arguments, shell history, or logs.
4. Run an independent redacting secret scanner across every rewritten ref and
   inspect object reachability/retention without displaying blob contents.
5. Peer-review the before/after ref map, intended removed paths, retained tags,
   and default branch tree.
6. Force-update only the approved refs during the maintenance window, restore
   branch protection, and re-run all required checks.
7. Expire server-side caches/reflogs according to the hosting provider's
   supported process; contact provider support when object purge guarantees are
   required.
8. Invalidate or delete CI caches/artifacts, release bundles, mirrors, and other
   derived copies that may contain the blobs.

## Clone and fork recovery

Notify every clone/fork owner that ordinary pull/merge can reintroduce the old
objects. Require a fresh clone from the rewritten repository or an explicitly
reviewed hard realignment with deletion of old refs and local object cleanup.
Close/rebase open PRs from clean commits. Rotate again if any old value is later
redistributed.

## Verification and closure

- every protected branch/tag points to the approved rewritten commit
- current-tree and introduced-commit secret CI pass
- an independent all-ref/object scan reports no affected artifact
- no deployment references an obsolete pre-rewrite commit/image by accident
- forks, mirrors, CI artifacts, releases, and caches have owners and closure
  evidence
- rotation/revocation remains confirmed; no rollback restores an old value or
  pre-rewrite ref

History rewriting reduces distribution; it cannot make an exposed credential
secret again. Provider revocation is the security boundary.
