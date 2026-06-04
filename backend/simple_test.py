"""
Einfacher Test für Rendering ohne externe Dependencies.
"""

import sys


class MockMessage:
    pass


def main() -> int:
    sys.modules['langchain_core'] = MockMessage
    sys.modules['langchain_core.messages'] = MockMessage
    sys.modules['app.services.langgraph'] = MockMessage
    sys.modules['app.services.langgraph.metrics'] = MockMessage
    sys.modules['app.services.langgraph.prompt_debug'] = MockMessage
    sys.path.insert(0, '/root/sealai/backend')
    try:
        from app.services.langgraph.prompting import render_with_validation
        result = render_with_validation('global_system_v2.jinja2', 'Test', {})
        print("Test erfolgreich: Prompt gerendert ohne Fehler.")
        print("Erste 100 Zeichen:", result[:100])
        return 0
    except Exception as e:
        print("Test fehlgeschlagen:", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
