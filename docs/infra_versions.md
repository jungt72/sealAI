# Infra Versions

Generated: 2025-12-27 14:59:25 UTC
Host: ubuntu-8gb-nbg1-1

## Container inventory
### docker compose ps
```
docker compose not available
```
### docker ps
```
CONTAINER ID   IMAGE                                    COMMAND                  CREATED       STATUS                 PORTS                                                                          NAMES
7d5a40268a2c   nginx:latest                             "/docker-entrypoint.…"   2 hours ago   Up 2 hours (healthy)   0.0.0.0:80->80/tcp, [::]:80->80/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp   nginx
b4b5ca996740   sealai-frontend                          "docker-entrypoint.s…"   2 hours ago   Up 2 hours (healthy)   0.0.0.0:3000->3000/tcp, [::]:3000->3000/tcp                                    frontend
6f06d761b0b6   sealai-backend:dev                       "uvicorn app.main:ap…"   2 hours ago   Up 2 hours (healthy)   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp                                    backend
a62e2e0ea205   ghcr.io/jungt72/sealai-keycloak:latest   "/opt/keycloak/bin/k…"   2 hours ago   Up 2 hours             8443/tcp, 0.0.0.0:8080->8080/tcp, [::]:8080->8080/tcp, 9000/tcp                keycloak
bcf25e0657d6   postgres:15                              "docker-entrypoint.s…"   2 hours ago   Up 2 hours (healthy)   5432/tcp                                                                       postgres
606826ca5da9   qdrant/qdrant:v1.15.0                    "./entrypoint.sh"        2 hours ago   Up 2 hours             0.0.0.0:6333-6334->6333-6334/tcp, [::]:6333-6334->6333-6334/tcp                qdrant
20f739c89b77   redis/redis-stack-server:7.4.0-v6        "/entrypoint.sh"         2 hours ago   Up 2 hours (healthy)   0.0.0.0:6379->6379/tcp, [::]:6379->6379/tcp                                    redis
```
### docker images
```
REPOSITORY                        TAG        IMAGE ID       CREATED        SIZE
sealai-frontend                   latest     dae5bbbff82c   2 hours ago    214MB
sealai-backend                    dev        e3eadddf1605   2 hours ago    775MB
ghcr.io/jungt72/sealai-keycloak   latest     9a8b72a6b3b6   2 hours ago    577MB
<none>                            <none>     1407ead7a546   3 days ago     214MB
<none>                            <none>     eec0511a759e   3 days ago     775MB
<none>                            <none>     12f6c264def5   4 days ago     577MB
nginx                             latest     576306625d79   2 weeks ago    152MB
postgres                          15         e07498b1e6cc   2 weeks ago    444MB
qdrant/qdrant                     v1.15.0    03bc8c3501aa   5 months ago   198MB
redis/redis-stack-server          7.4.0-v6   1ebedd176a23   5 months ago   513MB
```

## Services
### Postgres
- Container: postgres
- Image: postgres:15
- Ports: 5432/tcp
- Running version: PostgreSQL 15.15 (Debian 15.15-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
- Command/Query: docker exec postgres psql -U sealai -d sealai -c "SELECT version();"
- Notes: first attempt failed: the input device is not a TTY

### Qdrant
- Container: qdrant
- Image: qdrant/qdrant:v1.15.0
- Ports: 0.0.0.0:6333-6334->6333-6334/tcp, [::]:6333-6334->6333-6334/tcp
- Running version: 1.15.0
- Command/Query: curl http://127.0.0.1:6333/
- Notes: first attempt failed: OCI runtime exec failed: exec failed: unable to start container process: exec: "qdrant": executable file not found in $PATH: unknown

### Redis
- Container: redis
- Image: redis/redis-stack-server:7.4.0-v6
- Ports: 0.0.0.0:6379->6379/tcp, [::]:6379->6379/tcp
- Running version: 7.4.5
- Command/Query: docker exec redis redis-server --version

### Keycloak
- Container: keycloak
- Image: ghcr.io/jungt72/sealai-keycloak:latest
- Ports: 8443/tcp, 0.0.0.0:8080->8080/tcp, [::]:8080->8080/tcp, 9000/tcp
- Running version: Keycloak 25.0.4
JVM: 21.0.4 (Red Hat, Inc. OpenJDK 64-Bit Server VM 21.0.4+7-LTS)
OS: Linux 6.8.0-90-generic amd64
- Command/Query: docker exec keycloak /opt/keycloak/bin/kc.sh --version
- Image tag (from docker ps): ghcr.io/jungt72/sealai-keycloak:latest

### Strapi
- Container: strapi
- Image: not found
- Ports: not running
- Running version: 5.31.0
- Command/Query: python3 -c 'import json; ...' (strapi-backend/package.json)
- Service defined in compose: unknown
