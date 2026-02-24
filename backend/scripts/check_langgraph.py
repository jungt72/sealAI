try:
    from langgraph.types import Command
    print("Command_Found")
except ImportError:
    print("Command_Missing")

try:
    from langgraph.types import Send
    print("Send_Found")
except ImportError:
    print("Send_Missing")
