# Debug: pressure_bar invalid_parameters

## Minimal repro (Backend)

Set token in env (do not print it):

```bash
export AUTH_TOKEN="..."
```

Optional base URL override:

```bash
export BASE_URL="http://localhost:8000"
```

### a) String payload (expected: 400 invalid_parameters)

```bash
curl -sS -i "$BASE_URL/api/v1/langgraph/parameters/patch" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -d '{"chat_id":"debug-pressure","parameters":{"pressure_bar":"10 bar"}}'
```

### b) Numeric payload (expected: 200 ok)

```bash
curl -sS -i "$BASE_URL/api/v1/langgraph/parameters/patch" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -d '{"chat_id":"debug-pressure","parameters":{"pressure_bar":10}}'
```
