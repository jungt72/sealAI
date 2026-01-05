"""
Prompt Renderer Module – Best Practices für Jinja2-Templates

Dieses Modul rendert Jinja2-Templates sicher, mit Validierung, Logging und Defaults.
Verwendet für LangGraph-Prompts in SealAI.

Best Practices:
- Sichere Ersetzung von Variablen.
- Validierung auf verbleibende Platzhalter.
- Logging für Debugging.
- Kontext-Normalisierung für User-Input.
"""

import os
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, TemplateError
from typing import Dict, Any, Optional

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PromptRenderer:
    def __init__(self, template_dir: str = "/root/sealai/backend/app/services/langgraph/prompts"):
        self.template_dir = template_dir
        self.env = Environment(loader=FileSystemLoader(template_dir))
        # Füge globale Defaults hinzu
        self.env.globals.update({
            'today': datetime.now().strftime("%Y-%m-%d"),
            'company_name': 'SealAI',
            'domain': 'Sealing Technology',
            'language': 'de'
        })

    def normalize_context(self, user_input: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalisiere User-Input für Templates.
        Extrahiere Schlüsselwörter (z.B. 'details' -> detaillierte Anfrage).
        """
        normalized = context.copy()
        if 'details' in user_input.lower() or 'erkläre' in user_input.lower():
            normalized['request_type'] = 'detailed_explanation'
        elif 'empfehlung' in user_input.lower():
            normalized['request_type'] = 'recommendation'
        else:
            normalized['request_type'] = 'general'
        normalized['query'] = user_input
        return normalized

    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Rendert ein Template mit Validierung.
        """
        try:
            template = self.env.get_template(template_name)
            rendered = template.render(**context)
            # Validierung: Prüfe auf verbleibende {{ }}
            if '{{' in rendered or '}}' in rendered:
                logger.warning(f"Unvollständige Ersetzung in {template_name}: {rendered[:200]}...")
                raise ValueError("Template hat unvollständige Platzhalter.")
            logger.info(f"Template {template_name} erfolgreich gerendert.")
            return rendered
        except TemplateError as e:
            logger.error(f"Fehler beim Rendern von {template_name}: {e}")
            raise

    def render_with_validation(self, template_name: str, user_input: str, context: Dict[str, Any] = {}) -> str:
        """
        Vollständiger Rendering-Prozess: Normalisiere, rendere und validiere.
        """
        normalized_context = self.normalize_context(user_input, context)
        return self.render_template(template_name, normalized_context)

# Beispiel-Nutzung
if __name__ == "__main__":
    renderer = PromptRenderer()
    # Beispiel für material_agent
    result = renderer.render_with_validation("material_agent.jinja2", "Erkläre PTFE", {})
    print(result)