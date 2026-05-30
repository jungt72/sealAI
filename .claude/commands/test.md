---
description: Run focused tests for a scope and report exact commands + results
---
Run the smallest relevant test set for the scope below, then report the exact command(s) and a pass/fail summary. Never hide failures.

- Backend: cd backend && pytest tests/<file>.py -q  (full: pytest -q)
- Frontend: cd frontend && npm run test:run  (node: npm run test:node)

Scope: $ARGUMENTS
