# backend/app/services/prompt/prompt_utils.py

"""
Prompt-Utils: Generische Funktionen zum Laden beliebiger Prompt-Dateien
aus dem zentralen Prompt-Verzeichnis.
"""

import os

PROMPT_DIR = os.path.join(os.path.dirname(__file__), '..', 'prompts')

def load_prompt(name: str) -> str:
    """
    Lädt eine Prompt-Datei aus dem Prompt-Verzeichnis.

    Args:
        name (str): Dateiname der Prompt-Datei (z.B. 'summarization_prompt.txt')

    Returns:
        str: Inhalt des Prompts als String
    """
    path = os.path.join(PROMPT_DIR, name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Prompt-Datei nicht gefunden: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()
