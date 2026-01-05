import sys
try:
    from langgraph.checkpoint.redis import RedisSaver
except ImportError:
    print("Could not import RedisSaver")
    sys.exit(0)

try:
    method = RedisSaver.aget_tuple
    print(f"Method: {method}")
    print(f"Module: {method.__module__}")
    print(f"Qualname: {method.__qualname__}")
except AttributeError:
    print("RedisSaver has no aget_tuple method")
