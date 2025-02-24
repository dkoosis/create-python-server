"""CLI command implementations for create_mcp_server.

This module provides the core CLI commands for creating and managing MCP servers.
It integrates with the setup, project, and template subsystems to provide a 
complete interface for server management.
"""

import logging
import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

import click

from create_mcp_server.claude import has_claude_app, update_claude_config
from create_mcp_server.core.project import PyProject
from create_mcp_server.core.template import ServerTemplate
from create_mcp_server.server.config import ServerConfig
from create_mcp_server.server.manager import ServerManager
from create_mcp_server.utils.validation import check_package_name
from create_mcp_server.utils.process import ensure_uv_installed, ProcessError

# Configure logging
logger = logging.getLogger(__name__)

# Exit codes
EXIT_OK = 0
EXIT_INVALID_ARGS = 1 
EXIT_SETUP_ERROR = 2
EXIT_RUNTIME_ERROR = 3

def setup_logging(debug: bool = False) -> None:
    """Configure logging with proper format."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

@click.group()
@click.option('--debug/--no-debug', default=False, help="Enable debug logging")
def cli(debug: bool) -> None:
    """Create and manage MCP servers."""
    setup_logging(debug)

@cli.command()
@click.argument('name', required=False)
@click.option('--path', type=click.Path(path_type=Path), help='Project directory')
@click.option('--version', type=str, help='Server version')
@click.option('--description', type=str, help='Project description')
@click.option('--port', type=int, envvar='MCP_SERVER_PORT', default=8000,
              help='Server port (env: MCP_SERVER_PORT)')
@click.option('--claudeapp/--no-claudeapp', default=True, 
              help='Enable/disable Claude.app integration')
def create(
    name: Optional[str], 
    path: Optional[Path], 
    version: Optional[str],
    description: Optional[str], 
    port: int,
    claudeapp: bool
) -> None:
    """Create a new MCP server.
    
    Args:
        name: Project name (prompted if not provided)
        path: Project directory (default: current directory)
        version: Server version (default: 0.1.0)
        description: Project description
        port: Server port (default: 8000, env: MCP_SERVER_PORT)
        claudeapp: Whether to enable Claude.app integration
    """
    try:
        # Ensure UV is installed
        ensure_uv_installed()

        # Get project name, either from argument or prompt
        name = name or click.prompt("Project name", type=str)
        if not name:
            raise click.UsageError("Project name is required")

        # Validate project name
        is_valid, error = check_package_name(name)
        if not is_valid:
            raise click.UsageError(error)

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
        click.echo("\nCreating virtual environment...")
        subprocess.run(['uv', 'venv'], cwd=project_path, check=True)

        # Install dependencies (prompt for confirmation)
        deps = ['fastapi', 'uvicorn', 'jinja2', 'toml', 'python-dotenv']
        if click.confirm(f"\nInstall dependencies? ({', '.join(deps)})"):
            click.echo("\nInstalling dependencies...")
            subprocess.run(['uv', 'pip', 'install'] + deps, cwd=project_path, check=True)

        # Create pyproject.toml and get package name
        click.echo("\nGenerating project files...")
        pyproject = PyProject.create_default(
            project_path / 'pyproject.toml',
            name=name,
            version=version or '0.1.0',
            description=description or 'An MCP server'
        )
        package_name = pyproject.metadata.name

        # Generate project files
        server_config = ServerConfig(
            name=name,
            port=port,
            description=description or 'An MCP server'
        )
        
        # Validate server configuration
        if errors := server_config.validate():
            raise click.UsageError(
                "Invalid server configuration:\n" + "\n".join(errors)
            )

        template = ServerTemplate()
        template.create_server(
            project_path, 
            server_config,
            project_path / 'src' / package_name
        )

        # Handle Claude.app integration
        if claudeapp and has_claude_app():
            if click.confirm("\nRegister with Claude.app?", default=True):
                if not update_claude_config(name, project_path):
                    logger.warning("Failed to register with Claude.app")

        # Start the server
        click.echo("\nStarting server...")
        run_cmd = [
            'uv', 'run', 'uvicorn',
            f'{package_name}.server:app',
            '--reload',
            '--port', str(port)
        ]
        
        try:
            process = subprocess.Popen(
                run_cmd,
                cwd=project_path,
                env={
                    **os.environ,
                    'PYTHONPATH': str(project_path / 'src')
                }
            )

            # Print success message and instructions
            click.echo(f"\n✅ Created project '{name}' in '{project_path}'")
            click.echo("\n✅ Server is running!")
            click.echo("\nAPI endpoints:")
            click.echo(f"  http://localhost:{port}/       - Main endpoint")
            click.echo(f"  http://localhost:{port}/docs   - API documentation")
            click.echo("\nNext steps:")
            click.echo("1. Press Ctrl+C to stop the server")
            click.echo(f"2. The server code is in {project_path}/src/{package_name}/")
            click.echo("3. Edit the code and the server will auto-reload")
            
            # Wait for user to stop server
            try:
                process.wait()
            except KeyboardInterrupt:
                process.terminate()
                process.wait()
                click.echo("\nServer stopped")

        except ProcessError as e:
            logger.error(f"Failed to start server: {e}")
            sys.exit(EXIT_RUNTIME_ERROR)

    except click.UsageError as e:
        click.echo(f"\n❌ Error: {str(e)}", err=True)
        sys.exit(EXIT_INVALID_ARGS)
    except subprocess.CalledProcessError as e:
        click.echo(f"\n❌ Command failed: {e.cmd}", err=True)
        if e.stdout:
            click.echo(f"Output: {e.stdout.decode()}", err=True)
        if e.stderr:
            click.echo(f"Error: {e.stderr.decode()}", err=True)
        sys.exit(EXIT_SETUP_ERROR)
    except Exception as e:
        click.echo(f"\n❌ Error: {str(e)}", err=True)
        if '--debug' in sys.argv:
            raise
        sys.exit(EXIT_RUNTIME_ERROR)

if __name__ == '__main__':
    cli()