#!/usr/bin/env python3
"""OpenAI "challenger" review for sealAI production release gates.

Sends exactly ONE bounded chat-completion call per invocation. Deliberately
standalone -- it never imports or invokes anything under
backend/sealai_v2/eval/ (the paid multi-case eval/judge harness); that
budget-heavy path is out of reach from this script by construction.

This is advisory only. It never writes an approval document
(ops/production-release-gate10-approval.json or any
/etc/sealai/approvals/*.json) -- the gate schemas require
`owner_read_diff_confirmation` to be set only by the human owner after
personally reading the diff, and this tool does not touch that boundary.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "ops" / ".gate-challenges"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_MAX_COMPLETION_TOKENS = 1800

# The commit that implemented GATE-10 P1 phase 1 (served-tree + migration
# hash binding). Hardcoded deliberately for this pilot script's one job;
# update here if that work moves to a different commit.
GATE10_P1_COMMIT = "c32270fd"

SYSTEM_PROMPT = (
    'Du bist ein technischer Pruefer ("Challenger") fuer die Produktions-'
    "Freigabe-Gates der Firma sealingAI. Der Eigentuemer ist fachlich kein "
    "Software-Entwickler und trifft die Entscheidung am Ende selbst -- du "
    "lieferst KEINE verbindliche Freigabe, sondern eine ehrliche, "
    "verstaendliche Einschaetzung auf Deutsch. Wenn laut den Unterlagen "
    "aktuell gar kein Freigabepfad existiert, sag das explizit und schlage "
    "keine Umgehung vor. Sei konkret: was ist erledigt, was fehlt genau, was "
    "waere der naechste sinnvolle Einzelschritt."
)


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return result.stdout


def _truncate(label: str, text: str, cap: int) -> str:
    if len(text) <= cap:
        return f"### {label}\n{text}"
    return f"### {label} (gekuerzt, {len(text)} Zeichen gesamt, erste {cap} gezeigt)\n{text[:cap]}\n...[gekuerzt]..."


def gather_gate10_p1_context() -> str:
    freeze_doc = (REPO / "docs" / "ops" / "production-release-freeze.md").read_text(
        encoding="utf-8"
    )
    p1_diff = (
        _run(["git", "show", GATE10_P1_COMMIT])
        or f"(kein Diff gefunden fuer {GATE10_P1_COMMIT})"
    )
    recent_commits = _run(
        ["git", "log", "--oneline", "-30", "-i", "--grep=gate-10", "--grep=gate10"]
    )
    return "\n\n".join(
        [
            _truncate(
                "docs/ops/production-release-freeze.md (Volltext)", freeze_doc, 45_000
            ),
            _truncate(
                f"git show {GATE10_P1_COMMIT} (P1-Phase-1-Implementierung)",
                p1_diff,
                25_000,
            ),
            _truncate("Juengste GATE-10-bezogene Commits", recent_commits, 4_000),
        ]
    )


def call_openai(model: str, max_completion_tokens: int, context: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit(
            "OPENAI_API_KEY ist nicht gesetzt. Dieses Skript liest .env.prod "
            "nicht selbst -- vorher exportieren, z.B.:\n"
            "  export OPENAI_API_KEY=$(grep '^OPENAI_API_KEY=' .env.prod | cut -d= -f2-)"
        )

    user_prompt = (
        "Pruefe den aktuellen Stand von GATE-10 (Production Release Freeze) in "
        "sealAI. Unten stehen das Freeze-Dokument im Volltext und der Diff der "
        "P1-Phase-1-Implementierung (Hash-Bindung).\n\n"
        "Antworte GENAU in dieser Struktur, auf Deutsch:\n"
        "1. Kurzfassung (max. 3 Saetze)\n"
        "2. Tabelle: Anforderung | Status (erledigt/offen) | was konkret fehlt\n"
        "3. Naechster sinnvoll bearbeitbare Einzelschritt\n"
        "4. Ausdruecklicher Hinweis: existiert aktuell UEBERHAUPT ein Weg, GATE-10 "
        "freizugeben -- ja oder nein, und warum\n\n" + context
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_completion_tokens": max_completion_tokens,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        sys.exit(f"OpenAI-API-Fehler {exc.code}: {body}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI-Modell (Default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        default=DEFAULT_MAX_COMPLETION_TOKENS,
        help=f"Obergrenze fuer die Antwort (Default: {DEFAULT_MAX_COMPLETION_TOKENS})",
    )
    args = parser.parse_args()

    context = gather_gate10_p1_context()
    result = call_openai(args.model, args.max_completion_tokens, context)
    message = result["choices"][0]["message"]["content"]
    usage = result.get("usage", {})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUT_DIR / f"gate10-p1-{stamp}.md"
    out_path.write_text(
        f"# GATE-10 P1 Challenger-Bericht ({result.get('model', args.model)})\n\n"
        f"{message}\n\n---\nToken-Nutzung: {json.dumps(usage)}\n",
        encoding="utf-8",
    )

    print(message)
    print("\n---")
    print(f"Token-Nutzung: {usage}")
    print(f"Bericht gespeichert unter: {out_path}")


if __name__ == "__main__":
    main()
