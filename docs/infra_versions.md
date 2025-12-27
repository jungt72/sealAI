# Infra Versions

Generated: 2025-12-27 13:34:17 UTC
Host: ubuntu-8gb-nbg1-1

## Container inventory
### docker compose ps
```
docker compose not available
```
### docker ps
```
docker ps failed: permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: Get "http://%2Fvar%2Frun%2Fdocker.sock/v1.50/containers/json": dial unix /var/run/docker.sock: connect: operation not permitted
```
### docker images
```
docker not available
```

## Services
### Postgres
- Container: postgres
- Image: not found
- Ports: not running
- Running version: unknown
- Command/Query: not executed
- Notes: docker not accessible: permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: Get "http://%2Fvar%2Frun%2Fdocker.sock/v1.50/containers/json": dial unix /var/run/docker.sock: connect: operation not permitted

### Qdrant
- Container: qdrant
- Image: not found
- Ports: not running
- Running version: unknown
- Command/Query: curl http://127.0.0.1:6333/
- Notes: curl failed: curl: (7) Failed to connect to 127.0.0.1 port 6333 after 0 ms: Couldn't connect to server

### Redis
- Container: redis
- Image: not found
- Ports: not running
- Running version: unknown
- Command/Query: not executed
- Notes: docker not accessible: permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: Get "http://%2Fvar%2Frun%2Fdocker.sock/v1.50/containers/json": dial unix /var/run/docker.sock: connect: operation not permitted

### Keycloak
- Container: keycloak
- Image: not found
- Ports: not running
- Running version: unknown
- Command/Query: not executed
- Notes: docker not accessible: permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: Get "http://%2Fvar%2Frun%2Fdocker.sock/v1.50/containers/json": dial unix /var/run/docker.sock: connect: operation not permitted
- Image tag (from docker ps): unknown

### Strapi
- Container: strapi
- Image: not found
- Ports: not running
- Running version: 5.31.0
- Command/Query: python3 -c 'import json; ...' (strapi-backend/package.json)
- Service defined in compose: unknown
