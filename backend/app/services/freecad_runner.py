"""Utility helpers to run FreeCAD scripts inside the dedicated container."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List

import docker
from docker.errors import DockerException, NotFound
from fastapi import HTTPException, status
from jinja2 import Template

BASE_DIR = Path(__file__).resolve().parents[2]
BUILTIN_SCRIPT_DIR = BASE_DIR / "freecad-scripts"

FREECAD_SHARED_ROOT = Path(os.getenv("FREECAD_SHARED_ROOT", "/app/freecad"))
FREECAD_CONTAINER_NAME = os.getenv("FREECAD_CONTAINER_NAME", "freecad")
FREECAD_TIMEOUT_SECONDS = float(os.getenv("FREECAD_TIMEOUT_SECONDS", "60"))

FREECAD_TEMPLATE_DIR = FREECAD_SHARED_ROOT / "scripts"
FREECAD_JOB_DIR = FREECAD_SHARED_ROOT / "jobs"
FREECAD_OUTPUT_DIR = FREECAD_SHARED_ROOT / "outputs"


def _ensure_directories() -> None:
    for path in (FREECAD_SHARED_ROOT, FREECAD_TEMPLATE_DIR, FREECAD_JOB_DIR, FREECAD_OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _seed_builtin_scripts() -> None:
    if not BUILTIN_SCRIPT_DIR.exists():
        return
    for script in BUILTIN_SCRIPT_DIR.glob("*.py"):
        target = FREECAD_TEMPLATE_DIR / script.name
        if not target.exists():
            target.write_text(script.read_text(encoding="utf-8"), encoding="utf-8")


_ensure_directories()
_seed_builtin_scripts()


def _sanitize_path(script_path: str) -> PurePosixPath:
    candidate = PurePosixPath(script_path.strip())
    if candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="script_path must be relative and must not contain '..'.",
        )
    return candidate


async def run_freecad_script(script_path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Render the template, execute it inside the FreeCAD container, and return job info."""
    sanitized = _sanitize_path(script_path)
    template_file = (FREECAD_TEMPLATE_DIR / sanitized).resolve()
    if not template_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script '{sanitized}' not found in shared volume.",
        )
    try:
        template = Template(template_file.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - template parsing
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse script template: {exc}",
        ) from exc

    rendered_script = template.render(PARAMS_JSON=json.dumps(params))
    job_id = uuid.uuid4().hex
    job_dir = FREECAD_JOB_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    rendered_script_path = job_dir / template_file.name
    rendered_script_path.write_text(rendered_script, encoding="utf-8")

    output_dir = FREECAD_OUTPUT_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    container_script_path = PurePosixPath("/workspace") / rendered_script_path.relative_to(FREECAD_SHARED_ROOT)
    container_output_dir = PurePosixPath("/workspace") / output_dir.relative_to(FREECAD_SHARED_ROOT)
    env = {"FREECAD_OUTPUT_DIR": str(container_output_dir)}

    loop = asyncio.get_running_loop()
    try:
        exec_result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                _exec_in_container,
                container_script_path,
                env,
            ),
            timeout=FREECAD_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"FreeCAD execution exceeded {FREECAD_TIMEOUT_SECONDS}s timeout.",
        ) from exc

    stdout, stderr = _decode_streams(exec_result)
    if exec_result.get("ExitCode", 1) != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "FreeCAD execution failed", "stderr": stderr, "stdout": stdout},
        )

    output_files = _collect_outputs(output_dir)
    if not output_files:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="FreeCAD execution finished but produced no output files.",
        )

    return {
        "job_id": job_id,
        "script": str(sanitized),
        "stdout": stdout,
        "stderr": stderr,
        "outputs": output_files,
    }


def _exec_in_container(script_path: PurePosixPath, environment: Dict[str, str]) -> Dict[str, Any]:
    client = docker.from_env()
    try:
        container = client.containers.get(FREECAD_CONTAINER_NAME)
        exec_id = container.client.api.exec_create(
            container.id,
            cmd=["FreeCADCmd", str(script_path)],
            environment=environment,
            user="1000:1000",
        )
        output = container.client.api.exec_start(exec_id, demux=True)
        inspect = container.client.api.exec_inspect(exec_id)
        return {
            "ExitCode": inspect.get("ExitCode", 1),
            "output": output,
        }
    except NotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FreeCAD container '{FREECAD_CONTAINER_NAME}' not found.",
        ) from exc
    except DockerException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to talk to Docker daemon: {exc}",
        ) from exc
    finally:
        client.close()


def _decode_streams(exec_result: Dict[str, Any]) -> tuple[str, str]:
    stdout_data = []
    stderr_data = []
    output = exec_result.get("output")
    if isinstance(output, tuple):
        stdout_chunk, stderr_chunk = output
        if stdout_chunk:
            stdout_data.append(stdout_chunk.decode("utf-8", errors="replace"))
        if stderr_chunk:
            stderr_data.append(stderr_chunk.decode("utf-8", errors="replace"))
    elif output:
        stdout_data.append(output.decode("utf-8", errors="replace"))
    return "".join(stdout_data), "".join(stderr_data)


def _collect_outputs(output_dir: Path) -> List[str]:
    files = []
    for path in output_dir.glob("*"):
        if path.is_file():
            files.append(str(path.relative_to(FREECAD_SHARED_ROOT)))
    return files
