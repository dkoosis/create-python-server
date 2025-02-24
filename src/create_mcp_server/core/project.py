# src/create_mcp_server/core/project.py
from pathlib import Path

from create_mcp_server.core.pyproject import PyProject, update_pyproject_settings
from create_mcp_server.utils.process import run_uv_command  # We'll create a placeholder later

def create_project(
    path: Path,
    name: str,
    version: str,
    description: str,
) -> None:
    project_path = path / name
    project_path.mkdir(parents=True, exist_ok=True)

    # Initialize project with uv (Simplified - no uv for now)
    # run_uv_command(["init", "--name", name, "--package", "--app", "--quiet"], project_path)

    # Add dependencies (Simplified - no uv for now)
    # run_uv_command(["add", "mcp", "fastapi", "uvicorn"], project_path)

    # Create a basic pyproject.toml (Simplified)
    pyproject_path = project_path / "pyproject.toml"
    PyProject.create_default(pyproject_path, name, version, description)

    # Copy templates and install (Simplified - Placeholder)
    # copy_template(project_path, name, description, version)
    # update_pyproject_settings(project_path, version, description) #Already handled.
    print(f"Project {name} created at {project_path}")