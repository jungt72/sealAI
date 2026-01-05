# MIGRATION: Phase-1 - strukturierte Logs, Trace-IDs

import logging
import json

logger = logging.getLogger("langgraph")

def log_event(event: str, **data):
    logger.info(json.dumps({"event": event, **data}))