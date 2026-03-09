import os
import sys
from dotenv import load_dotenv

# Sicherstellen, dass das Projektverzeichnis im PYTHONPATH ist
sys.path.append(os.getcwd())

from src.main import run_agent

def main():
    """
    Live End-to-End Test (Phase E2).
    Dieser Test nutzt ein echtes LLM (gpt-4o-mini), um die Tool-Bindung 
    und die RAG-Integration unter Realbedingungen zu prüfen.
    """
    load_dotenv()
    
    if not os.getenv("OPENAI_API_KEY"):
        print("FEHLER: OPENAI_API_KEY nicht in .env gefunden!")
        sys.exit(1)
        
    query = "Wir wollen eine Anlage für konzentrierte Schwefelsäure bei 150°C auslegen. Welches Material empfiehlst du und welche Limits gelten?"
    
    print("\n=== SealAI Live End-to-End Test (Blueprint v1.3.1) ===")
    print(f"Modell: gpt-4o-mini")
    print(f"Modus: LIVE (use_mock=False)")
    print("====================================================\n")
    
    try:
        run_agent(query, use_mock=False)
    except Exception as e:
        print(f"\nEin Fehler ist während des Live-Tests aufgetreten: {e}")

if __name__ == "__main__":
    main()
