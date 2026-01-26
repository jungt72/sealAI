
import asyncio
import socket
import sys

TIMEOUT = 0.2

async def check_port(ip, port, name):
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=TIMEOUT
        )
        writer.close()
        await writer.wait_closed()
        print(f"FOUND {name} AT: {ip}:{port}")
        return (name, ip)
    except:
        return None

async def main():
    print("Scanning for Services (Redis:6379, PG:5432, Qdrant:6333)...")
    tasks = []
    # Previous success was 172.18.0.x, focus there but keep others
    subnets = ["172.18.0", "172.17.0", "172.19.0", "172.20.0"]
    
    ports = [
        (6379, "REDIS"),
        (5432, "POSTGRES"),
        (6333, "QDRANT")
    ]

    for subnet in subnets:
        for i in range(1, 15): 
            ip = f"{subnet}.{i}"
            for port, name in ports:
                tasks.append(check_port(ip, port, name))
            
    results = await asyncio.gather(*tasks)
    found = [r for r in results if r]
    
    print("-" * 20)
    for name, ip in found:
        print(f"{name} => {ip}")
    print("-" * 20)

if __name__ == "__main__":
    asyncio.run(main())
