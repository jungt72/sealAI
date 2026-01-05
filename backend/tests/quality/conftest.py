from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest


@pytest.fixture(scope="session")
def golden_prompts() -> List[Dict[str, Any]]:
    path = Path(__file__).parent / "golden_prompts" / "golden_prompts.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def stub_answers() -> Dict[str, str]:
    # Offline-only: deterministic "representative" answers for regression.
    # These can later be replaced by captured real model outputs.
    answers: Dict[str, str] = {
        "gp_01_design_baseline": (
            "## Kurz-Zusammenfassung\n"
            "- Du planst einen RWDR für Mineralöl bei 80°C, 5 bar, 50 mm Welle, 1200 rpm.\n"
            "- Damit ist eine erste Werkstoff-/Profil-Orientierung möglich, aber die finale Freigabe hängt von Einbauraum, Oberfläche und Toleranzen ab.\n\n"
            "## Empfehlung\n"
            "- Werkstoff: FKM als naheliegende Option für Öl + erhöhtes Temperaturniveau (Details verifizieren).\n"
            "- Profil/Design: Standard-RWDR mit geeigneter Vorspannung; bei Druck ggf. Druckstützring/Back-up-Strategie prüfen.\n\n"
            "## Annahmen\n"
            "- Druck ist dauerhaft 5 bar (nicht pulsierend/spitz).\n"
            "- Wellenoberfläche und Härte liegen im üblichen Bereich für RWDR.\n\n"
            "## Risiken\n"
            "- Bei hohen Druckspitzen, schlechter Oberflächenqualität oder Drall steigt Leckagerisiko.\n"
            "- Chemische Kompatibilität hängt von Additiven im Öl ab.\n\n"
            "## Nächste Schritte\n"
            "1) Einbauraum/Normabmessung und Rotationsrichtung klären.\n"
            "2) Wellen-Rauheit (Ra/Rz) und Härte angeben.\n"
            "3) Druckverlauf (konstant vs. pulsierend) bestätigen.\n"
        ),
        "gp_02_ask_missing": (
            "## Kurz-Zusammenfassung\n"
            "Du willst eine Dichtungsempfehlung, aber es fehlen die Randbedingungen.\n\n"
            "## Fehlende Angaben\n"
            "- Medium (Öl/Wasser/Chemikalie)\n"
            "- Temperatur (min/max)\n"
            "- Druck (konstant/pulsierend)\n"
            "- Bewegung (Rotation/Linear) + Geschwindigkeit\n"
            "- Geometrie (z. B. Wellen-Ø / Nut)\n\n"
            "## Nächste Schritte\n"
            "Nenne bitte Medium, Temperatur und Druck zuerst; danach kann ich gezielt Material und Profil eingrenzen.\n"
        ),
        "gp_03_troubleshooting_leakage": (
            "## Kurz-Zusammenfassung\n"
            "Leckage nach 2 Wochen plus Riefen deutet häufig auf Oberflächen-/Montage- oder Kontaminationsprobleme hin.\n\n"
            "## Hypothesen\n"
            "- Drall/Lead auf der Welle (Pumpwirkung) oder falsche Rotationsrichtung.\n"
            "- Montageverletzung der Lippe oder fehlende Einführhilfe.\n"
            "- Abrasive Partikel/Schmutz → Riefen → Leckagepfad.\n\n"
            "## Checks\n"
            "1) Wellenoberfläche messen (Ra/Rz) und auf Drall prüfen.\n"
            "2) Sichtprüfung der Lippe (Einkerbungen, Schnitte) und Montageprozess reviewen.\n"
            "3) Dichtkante/Schutzlippe und Schmutzausschluss (Staublippe/Abstreifer) bewerten.\n\n"
            "## Risiken\n"
            "- Wiederholte Ausfälle, wenn Kontamination nicht behoben wird.\n\n"
            "## Nächste Schritte\n"
            "- Sag mir: Wellenhärte, Ra/Rz, Rotationsrichtung, und ob Sand/Staub vorhanden ist.\n"
        ),
        "gp_04_material_comparison": (
            "## Kurz-Zusammenfassung\n"
            "Bei Mineralöl und 120°C sind NBR oft am Limit; FKM und PTFE sind typischerweise robuster, abhängig von Druck/Speed und Additiven.\n\n"
            "## Vergleich\n"
            "- NBR: oft gut für Mineralöl, aber Temperaturreserve begrenzt.\n"
            "- FKM: bessere Temperatur- und Chemikalienreserve bei vielen Ölen.\n"
            "- PTFE: sehr chemisch inert, aber Design/Abdichtungskonzept anders (Kriechen/Anpressung beachten).\n\n"
            "## Grenzen\n"
            "- Ohne Druck-/Speed-Profil und Oberflächenangaben ist das nur eine Einordnung.\n\n"
            "## Quellen\n"
            "- Dokument: Werkstoffübersicht | Abschnitt: Temperatur/Öl-Kompatibilität | Quelle: intern\n\n"
            "## Nächste Schritte\n"
            "- Wenn du Druck, Drehzahl und Wellenoberfläche gibst, kann ich die Auswahl präzisieren.\n"
        ),
        "gp_05_high_pressure": (
            "## Kurz-Zusammenfassung\n"
            "40 bar ist für klassische RWDR oft kritisch; es kann funktionieren nur mit passenden Designmaßnahmen oder Alternativen.\n\n"
            "## Machbarkeit\n"
            "- Prüfe Druckspitzen, Spaltmaß und Extrusionssicherheit.\n\n"
            "## Risiken\n"
            "- Extrusion/Blow-out, starke Wärmeentwicklung, schneller Verschleiß.\n\n"
            "## Alternativen\n"
            "- PTFE-gestützte Dichtsysteme, mehrstufige Dichtung, Labyrinth + Abstreifer, ggf. anderes Dichtprinzip.\n\n"
            "## Nächste Schritte\n"
            "- Bitte nenne Spaltmaß, Einbauraum, Drehzahlprofil und ob Druck pulsierend ist.\n"
        ),
        "gp_06_high_temp": (
            "## Kurz-Zusammenfassung\n"
            "220°C ist ein Hochtemperaturfall; klassische Elastomere sind häufig grenzwertig.\n\n"
            "## Werkstoffoptionen\n"
            "- Hochtemperatur-Optionen hängen stark von Medium/Atmosphäre ab; PTFE- oder Spezialwerkstoffe können sinnvoll sein.\n\n"
            "## Annahmen\n"
            "- Langsame Rotation und keine aggressiven Chemikalien.\n\n"
            "## Risiken\n"
            "- Thermische Alterung, Versprödung, Setzverhalten.\n\n"
            "## Quellen\n"
            "- Dokument: Temperaturgrenzen | Abschnitt: Hochtemperatur | Quelle: intern\n\n"
            "## Nächste Schritte\n"
            "- Kläre: tatsächliche Temperaturspitzen, Atmosphäre (oxidierend), und gewünschte Standzeit.\n"
        ),
        "gp_07_contamination_abrasive": (
            "## Kurz-Zusammenfassung\n"
            "Abrasive Partikel sind ein Haupttreiber für frühen Verschleiß; Design und Schmutzausschluss sind entscheidend.\n\n"
            "## Design-Hebel\n"
            "- Zusätzliche Staublippe/Abstreifer, besserer Schmutzschutz, ggf. Spülung/Schleuderscheibe.\n\n"
            "## Montage\n"
            "- Saubere Montage, keine Partikel im Einbauraum, geeignete Schmierung.\n\n"
            "## Risiken\n"
            "- Riefenbildung → Leckagepfad.\n\n"
            "## Nächste Schritte\n"
            "- Welche Partikelgröße/Anteil? Gibt es Druckspitzen?\n"
        ),
        "gp_08_lead_helix_direction": (
            "## Kurz-Zusammenfassung\n"
            "Drall/Lead kann eine Pumpwirkung erzeugen und damit Leckage fördern.\n\n"
            "## Erklärung\n"
            "- Bestimmte Oberflächenstrukturen wirken wie ein Gewinde und transportieren Medium entlang der Welle.\n\n"
            "## Gegenmaßnahmen\n"
            "- Oberflächenfinish/Schleifrichtung anpassen, Lead minimieren, Lippe/Design prüfen.\n\n"
            "## Checks\n"
            "1) Lead-Messung bzw. Vergleichsmuster.\n"
            "2) Rotationsrichtung und Einbaulage verifizieren.\n\n"
            "## Quellen\n"
            "- Dokument: Oberflächen/Lead | Abschnitt: Pumpwirkung | Quelle: intern\n\n"
            "## Nächste Schritte\n"
            "- Sag mir Rotationsrichtung und aktuelle Schleifprozesse.\n"
        ),
        "gp_09_installation_safe": (
            "## Kurz-Zusammenfassung\n"
            "Eine saubere und reproduzierbare Montage reduziert Leckagerisiko.\n\n"
            "## Checkliste\n"
            "1) Bauteile reinigen, Kanten entgraten.\n"
            "2) Dichtlippe leicht mit geeignetem Medium schmieren.\n"
            "3) Einführhilfe nutzen, Lippe nicht über scharfe Kanten ziehen.\n"
            "4) Einpresstiefe/Fluchtung prüfen.\n\n"
            "## Risiken\n"
            "- Trockene Montage oder beschädigte Lippe führt häufig zu frühem Ausfall.\n\n"
            "## Nächste Schritte\n"
            "- Wenn du Einbauraum und Rotationsrichtung gibst, kann ich die Checkliste anpassen.\n"
        ),
        "gp_10_lifetime_framing": (
            "## Kurz-Zusammenfassung\n"
            "Standzeit ist stark von Randbedingungen abhängig; intern sollte man mit Bandbreiten und Einflussfaktoren arbeiten, nicht mit Garantien.\n\n"
            "## Einflussfaktoren\n"
            "- Medium/Additive, Temperatur, Druckspitzen, Oberflächenqualität, Kontamination, Montage.\n\n"
            "## Annahmen\n"
            "- Saubere Umgebung und stabile Betriebsdaten.\n\n"
            "## Risiken\n"
            "- Unbekannte Additive oder Partikel können die Standzeit stark verkürzen.\n\n"
            "## Nächste Schritte\n"
            "- Definiere Messkriterien (Leckage, Verschleiß) und sammle Felddaten für eine belastbare Bandbreite.\n"
        ),
        "gp_11_out_of_scope_redirect": (
            "## Kurz-Zusammenfassung\n"
            "Käsekuchen fällt nicht in meinen Schwerpunkt.\n\n"
            "## Nächste Schritte\n"
            "Wenn du möchtest: Beschreibe kurz deinen Dichtungsfall (Medium, Temperatur, Druck, Bewegung), dann helfe ich dir gezielt weiter.\n"
        ),
        "gp_12_units_consistency": (
            "## Kurz-Zusammenfassung\n"
            "Wasser bei 10 bar und 20–60°C plus 3000 rpm ist anspruchsvoll; Auswahl hängt von Geometrie und Oberflächen ab.\n\n"
            "## Empfehlung\n"
            "- Gib Einbauraum/Typ an, dann kann ich Werkstoff/Profil präzisieren.\n\n"
            "## Risiken\n"
            "- Hohe Drehzahl kann Wärme/ Verschleiß treiben; Druckspitzen erhöhen Extrusionsrisiko.\n\n"
            "## Nächste Schritte\n"
            "- Bitte nenne Wellenoberfläche (Ra/Rz), Toleranzen und ob Druck pulsierend ist.\n"
        ),
    }

    # Enforce ChatGPT-level structure in the regression stubs.
    rag_ids = {"gp_04_material_comparison", "gp_06_high_temp", "gp_08_lead_helix_direction"}
    for key, text in list(answers.items()):
        if key in rag_ids:
            text = text.replace("## Quellen", "## Wissensdatenbank (Quellen)")
        if "## Allgemeines Fachwissen" not in text:
            text = (
                text.rstrip()
                + "\n\n## Allgemeines Fachwissen\n"
                + "- Typische Empfehlungen hängen stark von Medium, Temperatur, Druck, Geschwindigkeit und Oberflächenqualität ab.\n"
                + "- Wenn Randbedingungen unklar sind, formuliere ich Annahmen und nenne die wichtigsten Prüf-/Messpunkte.\n"
            )
        answers[key] = text

    return answers


@pytest.fixture()
def minimal_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Make importing app.core.config.Settings safe for offline tests.
    monkeypatch.setenv("postgres_user", "test")
    monkeypatch.setenv("postgres_password", "test")
    monkeypatch.setenv("postgres_host", "localhost")
    monkeypatch.setenv("postgres_port", "5432")
    monkeypatch.setenv("postgres_db", "test")
    monkeypatch.setenv("database_url", "postgresql+psycopg://test:test@localhost:5432/test")
    monkeypatch.setenv("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("openai_api_key", "dummy")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("qdrant_url", "http://localhost:6333")
    monkeypatch.setenv("qdrant_collection", "test")
    monkeypatch.setenv("redis_url", "redis://localhost:6379/0")
    monkeypatch.setenv("nextauth_url", "http://localhost:3000")
    monkeypatch.setenv("nextauth_secret", "dummy")
    monkeypatch.setenv("keycloak_issuer", "http://localhost:8080/realms/test")
    monkeypatch.setenv("keycloak_jwks_url", "http://localhost:8080/realms/test/certs")
    monkeypatch.setenv("keycloak_client_id", "dummy")
    monkeypatch.setenv("keycloak_client_secret", "dummy")
    monkeypatch.setenv("keycloak_expected_azp", "dummy")
