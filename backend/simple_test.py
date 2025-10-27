"""
Einfacher Test für Rendering ohne externe Dependencies.
"""

import os
import sys
from pathlib import Path

# Mock für fehlende Module
class MockMessage:
    pass

sys.modules['langchain_core'] = MockMessage
sys.modules['langchain_core.messages'] = MockMessage
sys.modules['app.services.langgraph'] = MockMessage
sys.modules['app.services.langgraph.metrics'] = MockMessage
sys.modules['app.services.langgraph.prompt_debug'] = MockMessage

# Füge Pfad hinzu
sys.path.insert(0, '/root/sealai/backend')

try:
    from app.services.langgraph.prompting import render_with_validation
    result = render_with_validation('global_system_v2.jinja2', 'Test', {})
    print("Test erfolgreich: Prompt gerendert ohne Fehler.")
    print("Erste 100 Zeichen:", result[:100])
except Exception as e:
    print("Test fehlgeschlagen:", e)