import os
import threading
import hashlib
from typing import Any, Dict, Optional, Tuple
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
        
        self._env = Environment(
            loader=FileSystemLoader(prompt_dir),
            undefined=StrictUndefined,  # CRITICAL: Fail-Fast on missing variables
            autoescape=False, # Prompts are text, not HTML
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, context: Dict[str, Any]) -> Tuple[str, str, str]:
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
            if not template_name.endswith(".j2"):
                template_name += ".j2"
                
            template = self._env.get_template(template_name)
            content = template.render(**context)
            
            # Fingerprint: SHA256 of content
            fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
            
            # Version: Extract from filename (e.g. system_v1.j2 -> v1)
            # Naive extraction: check for _vX.j2
            version = "unknown"
            base_name = os.path.basename(template_name)
            import re
            match = re.search(r"_(v\d+)\.j2$", base_name)
            if match:
                version = match.group(1)
            
            return content, fingerprint, version
            
        except TemplateNotFound:
            raise FileNotFoundError(f"Prompt template '{template_name}' not found.")
