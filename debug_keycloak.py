import argparse
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

def get_token(base_url, username, password):
    url = f"{base_url}/realms/master/protocol/openid-connect/token"
    data = urllib.parse.urlencode({
        "username": username,
        "password": password,
        "grant_type": "password",
        "client_id": "admin-cli"
    }).encode()
    
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())["access_token"]
    except urllib.error.HTTPError as e:
        print(f"[-] Auth Failed: {e.code} {e.read().decode()}")
        sys.exit(1)
    except Exception as e:
        print(f"[-] Connection Error: {e}")
        sys.exit(1)

def get_realms(base_url, token):
    url = f"{base_url}/admin/realms"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as response:
        return [r["id"] for r in json.loads(response.read().decode())]

def get_client(base_url, token, realm, client_id):
    # exact search using query param if supported, strictly we filter list
    url = f"{base_url}/admin/realms/{realm}/clients?clientId={client_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as response:
        clients = json.loads(response.read().decode())
        # Filter for exact match just in case
        return next((c for c in clients if c.get("clientId") == client_id), None)

def get_client_secret(base_url, token, realm, client_uuid):
    url = f"{base_url}/admin/realms/{realm}/clients/{client_uuid}/client-secret"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())["value"]
    except:
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--realm", default="sealAI")
    parser.add_argument("--client", default="nextauth")
    args = parser.parse_args()

    print(f"[*] Authenticating to {args.url} as {args.user}...")
    token = get_token(args.url, args.user, args.password)
    print("[+] Authenticated.")

    print("[*] Checking Realms...")
    realms = get_realms(args.url, token)
    if args.realm not in realms:
        print(f"[-] Realm '{args.realm}' NOT FOUND.")
        print(f"    Available: {realms}")
        # Case Insensitive Check
        found = next((r for r in realms if r.lower() == args.realm.lower()), None)
        if found:
            print(f"    !!! MISMATCH: Found '{found}' instead of '{args.realm}'")
    else:
        print(f"[+] Realm '{args.realm}' Found.")

    # Proceed with the found/requested realm
    target_realm = args.realm if args.realm in realms else next((r for r in realms if r.lower() == args.realm.lower()), args.realm)
    
    print(f"[*] Checking Client '{args.client}' in '{target_realm}'...")
    client = get_client(args.url, token, target_realm, args.client)
    
    if not client:
        print(f"[-] Client '{args.client}' NOT FOUND in {target_realm}")
        sys.exit(1)
        
    print(f"[+] Client Found: {client.get('clientId')} (ID: {client.get('id')})")
    print(f"    - Public: {client.get('publicClient')}")
    print(f"    - BearerOnly: {client.get('bearerOnly')}")
    print(f"    - RedirectURIs: {client.get('redirectUris')}")
    print(f"    - BaseUrl: {client.get('baseUrl')}")
    print(f"    - WebOrigins: {client.get('webOrigins')}")
    
    if not client.get('publicClient'):
        secret = get_client_secret(args.url, token, target_realm, client['id'])
        print(f"    - Secret: {secret}")
    
