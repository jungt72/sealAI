# Dependency policy

This repo uses two layers:

- `backend/requirements.txt` defines desired pins (may track latest).
- `backend/requirements-lock.txt` is the deploy lock for reproducible builds.

Production deployments should install from `backend/requirements-lock.txt`.

Update flow:
1) Regenerate the lock from the backend container image.
2) Run CI gates (tests in container + dependency sanity).
3) Release with the new lock file committed.
