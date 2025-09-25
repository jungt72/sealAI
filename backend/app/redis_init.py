import asyncio
import os
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

async def main():
    saver = AsyncRedisSaver(redis_url=os.environ["REDIS_URL"])
    await saver.asetup()      # idempotent
    print("✅  RediSearch-Index angelegt/aktualisiert")

asyncio.run(main())
