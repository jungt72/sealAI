import sys
import os

# Ensure app module can be imported
sys.path.append("/app")

from app.core.prompts import PromptLoader

def test_supervisor_prompt():
    print("Testing PromptLoader...")
    try:
        # PromptLoader should default to /app/app/prompts if we run from /app/scripts
        # But let's be explicit or rely on the default which uses __file__
        loader = PromptLoader() 
        print(f"Prompts directory: {loader.prompts_dir}")
    except Exception as e:
        print(f"❌ Failed to initialize PromptLoader: {e}")
        sys.exit(1)
    
    # Test data
    kwargs = {
        "user_text": "Hello",
        "domain": "auto",
        "params_json": "{}",
        "thread_memory": "",
        "user_profile": "",
        "rag_context": ""
    }
    
    try:
        result = loader.get_rendered("supervisor", **kwargs)
        print("✅ Supervisor Prompt Rendered Successfully")
        print(f"Version: {result['version']}")
        print(f"Hash: {result['hash']}")
        print(f"Content Preview: {result['content'][:50]}...")
        
        # Verify hash stability
        result2 = loader.get_rendered("supervisor", **kwargs)
        if result["hash"] != result2["hash"]:
             print("❌ Hash instability detected!")
             sys.exit(1)
        else:
             print("✅ Hash stability confirmed")

    except Exception as e:
        print(f"❌ Failed to render supervisor prompt: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_supervisor_prompt()
