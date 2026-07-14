# Immutable dashboard release root

This tracked directory is the only dashboard source mounted by production
Nginx. Generated state is deliberately ignored:

- `artifacts/<source-git-sha>-<artifact-sha256>/` contains read-only files and
  the canonical `release.json` manifest.
- `current` is a relative symlink to the verified release served by Nginx.
- `rollback` is a relative symlink to the previous verified release.
- `.prepare.lock` serializes no-clobber artifact materialization.

`npm run release:prepare` may create an artifact here, but it never creates or
changes `current` or `rollback`. Only the separately approved GATE-08 release
transaction may atomically replace those links. Do not edit, copy into, or
delete generated entries manually.
