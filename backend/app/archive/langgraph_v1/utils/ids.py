import uuid

def generate_thread_id() -> str:
    return f"thr-{uuid.uuid4()}"

def generate_trace_id() -> str:
    return f"trc-{uuid.uuid4()}"

def generate_message_id() -> str:
    return f"msg-{uuid.uuid4()}"
