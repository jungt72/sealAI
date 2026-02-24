import yaml
import hashlib
from pathlib import Path
from typing import Any, Dict
from jinja2 import Environment, FileSystemLoader, StrictUndefined

class PromptLoader:
    def __init__(self, prompts_dir: str = None):
        if prompts_dir:
            self.prompts_dir = Path(prompts_dir)
        else:
            # Default to app/prompts relative to this file (app/core/prompts.py -> app/prompts)
            self.prompts_dir = Path(__file__).parent.parent / "prompts"
        
        self.manifest_path = self.prompts_dir / "_manifest.yml"
        self._manifest = self._load_manifest()
        
        self._env = Environment(
            loader=FileSystemLoader(str(self.prompts_dir)),
            undefined=StrictUndefined,
            autoescape=False
        )

    def _load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found at {self.manifest_path}")
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def get_rendered(self, prompt_name: str, **kwargs) -> Dict[str, str]:
        if prompt_name not in self._manifest:
            raise ValueError(f"Prompt '{prompt_name}' not found in manifest")

        entry = self._manifest[prompt_name]
        template_file = entry["file"]
        version = str(entry["version"])

        template = self._env.get_template(template_file)
        rendered_content = template.render(**kwargs)
        
        content_hash = hashlib.sha256(rendered_content.encode("utf-8")).hexdigest()

        return {
            "content": rendered_content,
            "hash": content_hash,
            "version": version
        }
