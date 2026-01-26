
import asyncio
import httpx
import sys

async def check(ip):
    url = f"http://{ip}:6333/collections"
    try:
        async with httpx.AsyncClient(timeout=0.2) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                print(f"FOUND QDRANT AT: {ip}")
                return ip
    except:
        pass
    return None

async def main():
    print("Scanning for Qdrant...")
    tasks = []
    # Scan typical docker ranges
    subnets = ["172.17.0", "172.18.0", "172.19.0", "172.20.0", "172.21.0", "172.22.0", "172.23.0", "172.24.0"]
    
    for subnet in subnets:
        for i in range(1, 20): # Scan first 20 IPs
            ip = f"{subnet}.{i}"
            tasks.append(check(ip))
            
    results = await asyncio.gather(*tasks)
    found = [r for r in results if r]
    if not found:
        print("Scanned, but nothing found.")
    else:
        print(f"Success! Found: {found}")

if __name__ == "__main__":
    asyncio.run(main())
