import sys
import os

# Add the current directory to sys.path
sys.path.append(os.getcwd())

# Load .env manually
env_path = ".env"
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                # Remove quotes if present
                value = value.strip("'").strip('"')
                os.environ[key] = value
                # Also set lowercase/uppercase variants if needed by pydantic settings
                os.environ[key.upper()] = value
                os.environ[key.lower()] = value

# Mock missing vars if .env is incomplete for testing
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/db"
if "POSTGRES_SYNC_URL" not in os.environ:
    os.environ["POSTGRES_SYNC_URL"] = "postgresql://user:pass@localhost:5432/db"

try:
    from app.langgraph.compile import create_main_graph
    create_main_graph()
    print("Graph compiled successfully")
except Exception as e:
    print(f"Graph compilation failed: {e}")
    sys.exit(1)
