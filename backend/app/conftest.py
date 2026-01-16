import os
import sys

# Ensure `/app` is on sys.path so `import app` always works in container and local runs.
# This makes tests robust against different CWD or pytest rootdir detection.
ROOT = os.path.dirname(os.path.abspath(__file__))  # /app/app
PARENT = os.path.dirname(ROOT)                     # /app

if PARENT not in sys.path:
    sys.path.insert(0, PARENT)
