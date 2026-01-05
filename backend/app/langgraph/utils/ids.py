# MIGRATION: Phase-1 - thread_id, trace_id, message_id Utilities

import uuid

def generate_thread_id() -> str:
    return str(uuid.uuid4())

def generate_trace_id() -> str:
    return str(uuid.uuid4())

def generate_message_id() -> str:
    return str(uuid.uuid4())