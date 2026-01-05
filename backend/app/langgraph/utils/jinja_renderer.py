# MIGRATION: Phase-1 - Template-Lade-/Render-Util; pure functions

from jinja2 import Template
import os

def render_template(template_path: str, context: dict) -> str:
    with open(template_path, 'r') as f:
        template = Template(f.read())
    return template.render(**context)