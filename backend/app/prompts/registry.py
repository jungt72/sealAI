import os
import threading
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

class PromptRegistry:
    _instance = None
    _lock = threading.Lock()
    _env: Optional[Environment] = None

    def __new__(cls, base_dir: str = "app/prompts"):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(PromptRegistry, cls).__new__(cls)
                    cls._instance._initialize(base_dir)
        return cls._instance

    def _initialize(self, base_dir: str):
        # Allow override via env var for testing or different deployments
        prompt_dir = os.getenv("SEALAI_PROMPT_DIR", base_dir)
        self._prompt_dir = Path(prompt_dir)
        self._manifest = self._load_manifest()
        
        self._env = Environment(
            loader=FileSystemLoader(prompt_dir),
            undefined=StrictUndefined,  # CRITICAL: Fail-Fast on missing variables
            autoescape=False, # Prompts are text, not HTML
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _load_manifest(self) -> Dict[str, str]:
        manifest_path = self._prompt_dir / "_manifest.yml"
        if not manifest_path.exists():
            return {}
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        mapping = data.get("prompts", data)
        out: Dict[str, str] = {}
        if not isinstance(mapping, dict):
            return out
        for logical_name, value in mapping.items():
            if isinstance(value, str):
                out[str(logical_name)] = value
            elif isinstance(value, dict):
                default_ver = value.get("default")
                if isinstance(default_ver, str):
                    out[str(logical_name)] = default_ver
        return out

    @staticmethod
    def _strip_ext(template_name: str) -> str:
        return template_name[:-3] if template_name.endswith(".j2") else template_name

    @staticmethod
    def _major_from_semver(version: str) -> Optional[str]:
        match = re.match(r"^(\d+)\.\d+\.\d+$", version)
        return match.group(1) if match else None

    def _candidate_exists(self, relative_name: str) -> bool:
        return (self._prompt_dir / relative_name).exists()

    def _resolve_template_name(self, template_name: str, version: Optional[str] = None) -> str:
        requested = self._strip_ext(template_name)
        # Backward compatible explicit versioned names remain first-class.
        if self._candidate_exists(f"{requested}.j2"):
            return f"{requested}.j2"

        selected_version = version or self._manifest.get(requested)
        if selected_version:
            semver_candidate = f"{requested}_{selected_version}.j2"
            if self._candidate_exists(semver_candidate):
                return semver_candidate

            major = self._major_from_semver(selected_version)
            if major:
                legacy_major_candidate = f"{requested}_v{major}.j2"
                if self._candidate_exists(legacy_major_candidate):
                    return legacy_major_candidate

        return f"{requested}.j2"

    @staticmethod
    def _extract_version(template_name: str) -> str:
        base_name = os.path.basename(template_name)
        semver_match = re.search(r"_(\d+\.\d+\.\d+)\.j2$", base_name)
        if semver_match:
            return semver_match.group(1)
        legacy_match = re.search(r"_(v\d+)\.j2$", base_name)
        if legacy_match:
            return legacy_match.group(1)
        return "unknown"

    def render(self, template_name: str, context: Dict[str, Any], version: Optional[str] = None) -> Tuple[str, str, str]:
        """
        Renders a template with the given context.
        Returns:
            (content, fingerprint, version)
        Raises:
            jinja2.UndefinedError if variables are missing.
            FileNotFoundError if template is missing.
        """
        if not self._env:
            raise RuntimeError("PromptRegistry not initialized. Call __init__ first.")
        
        try:
            template_name = self._resolve_template_name(template_name, version=version)
            template = self._env.get_template(template_name)
            content = template.render(**context)
            
            # Fingerprint: SHA256 of content
            fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
            
            return content, fingerprint, self._extract_version(template_name)
            
        except TemplateNotFound:
            raise FileNotFoundError(f"Prompt template '{template_name}' not found.")
