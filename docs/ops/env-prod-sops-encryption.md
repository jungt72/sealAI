# `.env.prod` encryption at rest (sops + age)

Added 2026-07-18. Solves two gaps in the previous plaintext-only setup:
production secrets had no offsite backup and no audit trail of who changed
what, when — because the plaintext file could never safely go into git.

## How it works

- `.env.prod` (plaintext, 0600, gitignored) is still the file every deploy
  script and `docker compose --env-file .env.prod` actually reads. Nothing
  about the live workflow changes.
- `ops/env-prod.sops` is the same file with every *value* encrypted
  (`sops`+`age`, per-key, dotenv codec) — keys stay readable so a `git diff`
  shows which secret changed, never its content. This file **is** committed
  to git: encryption is the reason that's safe. It deliberately does not live
  at an `.env*`-shaped path: `ops/check-secret-hygiene.py`'s `filename.env`
  rule rejects any committed file that merely looks like an env file by name,
  regardless of content, and that blanket rule is not something to carve an
  exception into just for this.
- `.sops.yaml` (repo root, committed) pins the `age` **public** key used for
  encryption. The matching private key lives only at
  `~/.config/sops/age/keys.txt` on the VPS (mode 600, never committed,
  sops' own default lookup path — no extra config needed to find it).

## Day-to-day workflow

Edit `.env.prod` exactly as before, then:

```
ops/env_prod_sops_encrypt.sh
git add ops/env-prod.sops
git commit -m "chore(env): update ops/env-prod.sops"
```

To reconstruct `.env.prod` from git history (new box, disaster recovery,
or checking what a past value used to be):

```
ops/env_prod_sops_decrypt.sh          # refuses to overwrite an existing .env.prod
FORCE=1 ops/env_prod_sops_decrypt.sh  # backs up the existing file first, then overwrites
```

Both scripts require the `sops` binary; on this VPS it's a manually-installed
static binary at `~/bin/sops` (not from apt — apt doesn't package it), verified
against the official `getsops/sops` sigstore signature via `cosign verify-blob`
at install time. `age`/`age-keygen` are the official Ubuntu `age` package.

## What this does NOT do

- It does not touch `release-backend-v2.sh` or any deploy path — decryption
  is a manual step you run when you need to reconstruct the file, not part
  of the deploy sequence. Wiring it into deploy automation is a deliberate
  follow-up decision, not done here.
- It does not cover `.env.prod.staging` or any other env file yet — `.sops.yaml`
  only matches `.env.prod`/`ops/env-prod.sops` today. Extend the `path_regex`
  there (and re-run the encrypt script for that file) if you want the same
  treatment elsewhere.
- Blank lines used purely for visual grouping in `.env.prod` are not
  preserved through an encrypt/decrypt round-trip (a documented limitation of
  sops' dotenv codec) — every actual key, value, and comment is (verified
  byte-for-byte on the initial encryption).

## Key loss

If `~/.config/sops/age/keys.txt` is ever lost with no other copy, every
historical `ops/env-prod.sops` becomes permanently unreadable. This is a single
point of failure by design (that's what "only the VPS can decrypt this"
means) — back that key file up somewhere you control outside this VPS if you
want protection against total VPS loss, since the disk-loss incident on
2026-07-02 is exactly the scenario this key would need to survive.
