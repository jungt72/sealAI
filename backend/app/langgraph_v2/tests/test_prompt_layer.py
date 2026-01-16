
import sys
import os
sys.path.append("/app")
import pytest
from pathlib import Path
from unittest.mock import patch
from jinja2 import StrictUndefined
from app.langgraph_v2.utils import jinja

# Helper to isolate environment state
@pytest.fixture(autouse=True)
def clear_env_cache():
    jinja._env.cache_clear()
    yield
    jinja._env.cache_clear()

def test_render_default_template(tmp_path):
    # Setup dummy prompts dir
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "greet.j2").write_text("Hello {{ name }}!")

    # Patch PROMPTS_DIR
    with patch("app.langgraph_v2.utils.jinja.PROMPTS_DIR", prompts_dir):
        result = jinja.render_template("greet.j2", {"name": "World"})
        assert result == "Hello World!"

def test_render_tenant_override(tmp_path):
    # Setup dummy prompts dir
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    
    # Default
    (prompts_dir / "greet.j2").write_text("Hello {{ name }} (Default)")
    
    # Tenant 'acme'
    acme_dir = prompts_dir / "acme"
    acme_dir.mkdir()
    (acme_dir / "greet.j2").write_text("Greetings from Acme, {{ name }}!")

    with patch("app.langgraph_v2.utils.jinja.PROMPTS_DIR", prompts_dir):
        # 1. Test Default (no tenant)
        res_default = jinja.render_template("greet.j2", {"name": "User"})
        assert res_default == "Hello User (Default)"

        # 2. Test Tenant with Override
        res_acme = jinja.render_template("greet.j2", {"name": "User"}, tenant_id="acme")
        assert res_acme == "Greetings from Acme, User!"

        # 3. Test Tenant WITHOUT Override (Fallback)
        # 'other_corp' has no folder
        res_other = jinja.render_template("greet.j2", {"name": "User"}, tenant_id="other_corp")
        assert res_other == "Hello User (Default)"

def test_strict_undefined_raises(tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "broken.j2").write_text("Hello {{ missing_var }}")

    with patch("app.langgraph_v2.utils.jinja.PROMPTS_DIR", prompts_dir):
        with pytest.raises(Exception) as excinfo:
            jinja.render_template("broken.j2", {})
        # Should be jinja2.UndefinedError
        assert "missing_var" in str(excinfo.value)
