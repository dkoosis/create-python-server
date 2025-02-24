"""CLI command implementations for create_mcp_server.

File: /Users/davidkoosis/projects/create_mcp_server/src/create_mcp_server/cli/commands.py

This module provides the core CLI commands for creating and managing MCP servers.
It integrates with the setup, project, and template subsystems to provide a 
complete interface for server management.

Key commands:
- create: Initialize a new MCP server project
- check-imports: Validate Python imports in a project
- start: Start an MCP server
- status: Check server status
"""

import logging
import sys
import subprocess
from pathlib import Path
from typing import Optional

import click
import toml

from create_mcp_server.claude import has_claude_app, update_claude_config
from create_mcp_server.core.project import PyProject
from create_mcp_server.core.template import ServerTemplate
from create_mcp_server.server.config import ServerConfig
from create_mcp_server.server.manager import ServerManager
from create_mcp_server.utils.setup import ProjectSetup, SetupError
from create_mcp_server.utils.prompts import (
    prompt_project_name,
    prompt_project_version,
    prompt_project_path,
    prompt_server_config,
    confirm_project_creation
)

# Configure logging
logger = logging.getLogger(__name__)

# Exit codes
EXIT_OK = 0
EXIT_INVALID_ARGS = 1 
EXIT_SETUP_ERROR = 2
EXIT_RUNTIME_ERROR = 3

@click.group()
@click.option('--debug/--no-debug', default=False, help="Enable debug logging")
def cli(debug: bool) -> None:
    """Create and manage MCP servers.
    
    This tool helps you create and manage Model Context Protocol (MCP) servers
    that provide standardized data access for LLMs.
    """
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=log_level)

@cli.command()
@click.argument('name', required=False)
@click.option('--path', type=click.Path(path_type=Path), help='Project directory')
@click.option('--version', type=str, help='Server version')
@click.option('--description', type=str, help='Project description')
@click.option('--claudeapp/--no-claudeapp', default=True, help='Enable/disable Claude.app integration')
def create(name: Optional[str], path: Optional[Path], version: Optional[str], description: Optional[str], claudeapp: bool) -> None:
    """Create a new MCP server."""
    try:
        # Get project name, either from argument or prompt
        name = name or click.prompt("Project name", type=str)
        if not name:
            raise click.UsageError("Project name is required")

        # Get parent directory and create project path
        parent_dir = path or Path.cwd()
        project_path = parent_dir / name

        # Check if the directory already exists
        if project_path.exists():
            if not click.confirm(f"Directory '{project_path}' already exists. Overwrite?"):
                raise click.Abort()

        # Create the project directory
        project_path.mkdir(parents=True, exist_ok=True)

        # Create virtual environment
        subprocess.run(['uv', 'venv'], cwd=project_path, check=True)

        # Install dependencies (prompt for confirmation)
        if click.confirm("Install dependencies (fastapi, uvicorn, jinja2, toml, python-dotenv)?"):
            subprocess.run(['uv', 'pip', 'install', 'fastapi', 'uvicorn', 'jinja2', 'toml', 'python-dotenv'], cwd=project_path, check=True)

        # Parse pyproject.toml
        pyproject = PyProject(project_path / 'pyproject.toml')
        package_name = pyproject.metadata.name

        # Generate project files
        template = ServerTemplate()
        template.create_server(project_path, ServerConfig(name=name), project_path / 'src' / package_name)

        # Start the server
        subprocess.run(['uv', 'run', 'uvicorn', f'{package_name}.main:app', '--reload'], cwd=project_path, check=True)

        # Print instructions
        click.echo(f"\n✅ Created project '{name}' in '{project_path}'")
        click.echo("\n✅ Server is running!")
        click.echo("\nPress Ctrl+C to stop the server")

    except FileExistsError:
        click.echo(f"❌ Error: Directory '{project_path}' already exists. Please choose a different name or location.", err=True)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Error: Failed to execute command: {e.cmd}", err=True)
        click.echo(e.stderr, err=True)
        sys.exit(1)
    except toml.TomlDecodeError as e:
        click.echo(f"❌ Error: Failed to parse 'pyproject.toml': {e}", err=True)
        sys.exit(1)
    except FileNotFoundError as e:
        click.echo(f"❌ Error: File not found: {e.filename}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)

@cli.command(name='check-imports')
@click.argument('path', type=click.Path(exists=True, path_type=Path))
def check_imports(path: Path) -> None:
    """Check Python import hygiene in a project.
    
    PATH is the root directory of the project to check.
    """
    try:
        # Load project to get package directory
        pyproject = PyProject(path / "pyproject.toml")
        package_dir = path / "src" / pyproject.metadata.name

        # Run import check
        setup = ProjectSetup(path, pyproject.metadata.name)
        issues = setup.check_imports()

        # Report issues
        errors = [i for i in issues if i.is_error]
        warnings = [i for i in issues if not i.is_error]

        for warning in warnings:
            click.echo(
                f"Warning: {warning.file}:{warning.line} - {warning.message}",
                err=True
            )

        for error in errors:
            click.echo(
                f"Error: {error.file}:{error.line} - {error.message}",
                err=True
            )

        if errors:
            click.echo(f"\nFound {len(errors)} errors.", err=True)
            sys.exit(EXIT_SETUP_ERROR)
        elif warnings:
            click.echo(f"\nFound {len(warnings)} warnings.")
        else:
            click.echo("No import issues found.")

    except Exception as e:
        click.echo(f"❌ Error checking imports: {e}", err=True)
        sys.exit(EXIT_RUNTIME_ERROR)

@cli.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.option('--port', type=int, default=8000, help="Server port")
@click.option('--host', type=str, default="127.0.0.1", help="Server host")
def start(path: Path, port: int, host: str) -> None:
    """Start an MCP server."""
    try:
        # Load project
        pyproject = PyProject(path / "pyproject.toml")
        
        # Create and start server
        config = ServerConfig(
            name=pyproject.metadata.name,
            port=port,
            host=host
        )
        
        server = ServerManager(path, pyproject.metadata.name, config)
        server.start()
        
    except Exception as e:
        click.echo(f"❌ Failed to start server: {e}", err=True)
        sys.exit(EXIT_RUNTIME_ERROR)

@cli.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
def stop(path: Path) -> None:
    """Stop a running MCP server."""
    try:
        pyproject = PyProject(path / "pyproject.toml")
        server = ServerManager(path, pyproject.metadata.name)
        server.stop()
        click.echo("✅ Server stopped")
        
    except Exception as e:
        click.echo(f"❌ Failed to stop server: {e}", err=True)
        sys.exit(EXIT_RUNTIME_ERROR)

@cli.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
def status(path: Path) -> None:
    """Check MCP server status."""
    try:
        pyproject = PyProject(path / "pyproject.toml")
        server = ServerManager(path, pyproject.metadata.name)
        status = server.get_status()
        
        click.echo(f"Server: {pyproject.metadata.name}")
        click.echo(f"Status: {'Running' if status.running else 'Stopped'}")
        
        if status.running:
            click.echo(f"PID: {status.pid}")
            click.echo(f"Uptime: {status.uptime}")
            click.echo(f"Memory: {status.memory_usage:.1f} MB")
            click.echo(f"CPU: {status.cpu_percent:.1f}%")
        
    except Exception as e:
        click.echo(f"❌ Error checking status: {e}", err=True)
        sys.exit(EXIT_RUNTIME_ERROR)

if __name__ == '__main__':
    cli()