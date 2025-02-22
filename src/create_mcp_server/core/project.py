"""Project creation and management."""
from pathlib import Path
from create_mcp_server.core.template import copy_template
from create_mcp_server.core.pyproject import update_pyproject_settings
from create_mcp_server.utils.process import run_uv_command

def create_project(
    path: Path,
    name: str,
    version: str,
    description: str,
    **kwargs
) -> None:
    """Create a new MCP server project."""
    path.mkdir(parents=True, exist_ok=True)

    # Initialize project with uv
    run_uv_command(["init", "--name", name, "--package", "--app", "--quiet"], path)
    
    # Add dependencies
    run_uv_command(["add", "mcp", "fastapi", "uvicorn"], path)

    # Copy templates and install
    copy_template(path, name, description, version)
    update_pyproject_settings(path, version, description)
