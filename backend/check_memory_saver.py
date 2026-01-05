import asyncio
import sys

try:
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:
    print("Could not import MemorySaver")
    sys.exit(1)

async def main():
    saver = MemorySaver()
    print(f"Has aget_tuple: {hasattr(saver, 'aget_tuple')}")
    try:
        # Just call it to see if it raises NotImplementedError
        # We don't care about the result or config correctness for this check
        await saver.aget_tuple({"configurable": {"thread_id": "1"}})
        print("aget_tuple worked (or at least didn't raise NotImplementedError)")
    except NotImplementedError:
        print("aget_tuple raised NotImplementedError")
    except Exception as e:
        # Other errors are fine (e.g. key error), as long as it's not NotImplementedError from base
        print(f"aget_tuple raised {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
