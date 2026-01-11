# Dependency policy

This repo uses two layers:

- `backend/requirements.txt` defines desired pins (may track latest).
- `backend/requirements-lock.txt` is the deploy lock for reproducible builds.

Production deployments should install from `backend/requirements-lock.txt`.
For container builds, set `BACKEND_USE_REQUIREMENTS_LOCK=1` so the backend image uses the lock file.

Update flow:
1) Edit `backend/requirements.txt` with latest desired pins.
2) Run `ops/check_backend_requirements_latest.sh` to validate resolvability.
3) If green, regenerate the lock from the backend container image.
4) Run CI gates (tests in container + dependency sanity).
5) Release with the new lock file committed.

Triage guidance for pip-audit:
- Confirm the vulnerable package is present in `backend/requirements-lock.txt`.
- Check if a fixed version exists and update `backend/requirements.txt` accordingly.
- Regenerate the lock and rerun the gates before release.
