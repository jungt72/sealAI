# Fail-closed Agent Relay

`ops/agent_relay.py` implements a bounded local workflow:

1. Build Contract
2. read-only Claude Contract Audit
3. Codex implementation
4. deterministic local tests
5. read-only Claude Diff Audit
6. at most one scoped remediation and a second Diff Audit
7. draft pull request after a separate explicit command and human review

It never installs or logs in to Claude, never falls back to an Anthropic API
key, never stages or commits files, never pushes a branch, and never merges,
deploys, queries production, or performs cleanup. The compatibility wrapper
`ops/relay.sh` requires a repository-local virtual environment (or an explicit
absolute `SEALAI_RELAY_PYTHON`), verifies the four required local packages, and
then executes the Python entry point in isolated mode. It never installs
dependencies itself.

Prepare the manual local runtime once, without production credentials:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r backend/requirements-dev.txt
```

Dependency installation is a manual workstation action. The relay remains
`BLOCKED_EXTERNAL` when the interpreter or packages are unavailable.

## Contract and bundle

The JSON-schema-validated YAML contract freezes the exact baseline, allowed
paths, deterministic test argv, migration/security/rollback/risk plans, Claude
model and budget, and the draft-PR target. For a new increment, create the
contract beneath the ignored `.ai-remediation/local-contracts/` directory so it
can bind the current clean commit without a self-referential Git commit.
`prepare` copies it into an immutable local bundle beneath
`.ai-remediation/relay-runs/<contract_id>/`.

The bundle always starts with these files:

- `build-contract.yaml`
- `repository-fingerprint.json`
- `production-fingerprint.json`
- `implementation.diff`
- `changed-files.txt`
- `test-results.json`
- `migration-plan.yaml`
- `security-impact.yaml`
- `rollback-plan.yaml`
- `known-risks.yaml`

Only an already-versioned, explicitly redacted local production fingerprint is
accepted. `contains_secret_values` must be false. No production refresh is
performed. Repository inputs and outputs are bounded regular files; path
escapes, symlinks, file swaps, dirty or changed baselines, out-of-scope files,
unexpected test mutations, oversized diffs, and high-confidence credential
canaries fail closed. Child processes receive argv arrays with `shell=False`;
test execution is limited to pytest and Ruff.

Example sequence, from a clean topic worktree:

```bash
ops/relay.sh \
  --contract .ai-remediation/local-contracts/my-increment.yaml prepare

ops/relay.sh \
  --contract .ai-remediation/local-contracts/my-increment.yaml contract-audit

# Codex implements only the frozen scope. Then:
ops/relay.sh \
  --contract .ai-remediation/local-contracts/my-increment.yaml capture

ops/relay.sh \
  --contract .ai-remediation/local-contracts/my-increment.yaml \
  diff-audit --iteration 1
```

After a `BLOCK`, fix only the listed in-scope findings, run `capture` again, and
run Diff Audit iteration 2. There is no third review. A `LIMIT_REACHED` response
pauses the workflow without retrying or selecting a larger model.

## Claude boundary

Claude CLI receives no built-in tools. The complete canonical, bounded,
secret-scanned audit bundle and response schema are supplied as untrusted data
over standard input. The relay uses Claude Code safe mode, `--tools ""`, an
empty additive allowlist, a wildcard denylist, strict empty MCP configuration,
and disabled hooks, skills/commands, Chrome, and session persistence. This
prevents project/user settings, plugins, MCP tools, browser tools, remembered
sessions, and repository reads from expanding the audit surface. Its result
must be strict JSON under
`.ai-remediation/schemas/agent-relay-audit-response.schema.json` and must
self-report no writes or network tools. Raw Claude output is not persisted; only
the validated response plus bounded byte counts and SHA-256 digests are
recorded. The wrapper removes `ANTHROPIC_API_KEY` and other provider environment
variables, so subscription authentication cannot silently fall back to paid API
credentials. A Claude CLI too old to support these isolation flags fails as an
external blocker; the relay never retries with weaker permissions.

The Claude service transport is necessarily external, but Claude has no
network-capable repository tool. If the CLI is missing, unauthenticated, or
quota-limited, the state is `BLOCKED_EXTERNAL`. Installation and one-time login
are manual. The relay makes no install, login, retry, or API call on the user's
behalf.

## Draft PR gate

`draft-pr` is deliberately separate. It requires a passed second-stage gate, a
clean manually committed topic branch, and an upstream already equal to local
HEAD. It does not push. If `gh` is missing, unauthenticated, or cannot reach
GitHub, the result is `BLOCKED_EXTERNAL`. The only permitted external mutation
is creation of a draft PR; automatic merge and deployment remain impossible.
