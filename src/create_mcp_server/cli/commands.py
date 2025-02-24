import logging
import sys
from pathlib import Path
from typing import Optional

import click

from ..claude import has_claude_app, update_claude_config
from ..config import ServerConfig
from ..core.project import PyProject
from ..core.template import ServerTemplate, TemplateError
from ..server.manager import ServerManager
from ..utils.process import ensure_uv_installed
from ..utils.validation import check_package_name


logger = logging.getLogger(__name__)

# Exit codes
EXIT_OK = 0
EXIT_INVALID_ARGS = 1
EXIT_TEMPLATE_ERROR = 2
EXIT_RUNTIME_ERROR = 3

@click.group()
@click.option('--debug/--no-debug', default=False, help="Enable debug logging")
def cli(debug: bool) -> None:
    """Create and manage MCP servers.
    
    This tool helps you create new MCP servers from templates and
    manage their lifecycle.
    """
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=log_level)

def load_project(path: Path) -> PyProject:
    """Load the project configuration from pyproject.toml."""
    try:
        pyproject = PyProject(path / "pyproject.toml")
        return pyproject
    except Exception as e:
        click.echo(f"❌ Error loading project: {e}", err=True)
        sys.exit(EXIT_RUNTIME_ERROR)

@cli.command()
@click.option('--path', type=click.Path(path_type=Path), help="Project directory")
@click.option('--name', type=str, help="Project name")
@click.option('--version', type=str, help="Server version")
@click.option('--description', type=str, help="Project description")
@click.option('--claudeapp/--no-claudeapp', default=True, 
              help="Enable/disable Claude.app integration")
def create(
    path: Optional[Path],
    name: Optional[str],
    version: Optional[str],
    description: Optional[str],
    claudeapp: bool
) -> None:
    """Create a new MCP server project."""
    try:
        # Verify uv installation
        ensure_uv_installed()
        
        # Get project details
        name = click.prompt("Project name", type=str) if name is None else name
        if not name:
            click.echo("❌ Project name is required", err=True)
            sys.exit(EXIT_INVALID_ARGS)
            
        if not check_package_name(name):
            sys.exit(EXIT_INVALID_ARGS)
            
        description = (
            click.prompt("Project description", type=str, default="An MCP server")
            if description is None else description
        )
        
        version = (
            click.prompt("Project version", type=str, default="0.1.0")
            if version is None else version
        )
        
        # Set up paths
        project_path = (Path.cwd() / name) if path is None else path
        if path is None and project_path.exists():
            if not click.confirm(f"{project_path} exists. Use anyway?"):
                project_path = Path(
                    click.prompt("Enter project path", type=click.Path(path_type=Path))
                )
                
        # Create configuration
        config = ServerConfig(
            name=name,
            version=version,
            description=description
        )
        
        # Initialize project
        logger.info(f"Creating project in {project_path}")
        pyproject = PyProject.create_default(
            project_path / "pyproject.toml",
            name=name,
            version=version,
            description=description
        )
        
        # Create server from template
        template = ServerTemplate()
        package_dir = project_path / "src" / name
        template.create_server(project_path, config, package_dir)
        
        # Validate output
        errors = template.validate_output(project_path)
        if errors:
            for error in errors:
                click.echo(f"❌ {error}", err=True)
            sys.exit(EXIT_TEMPLATE_ERROR)
            
        # Handle Claude.app integration
        if (
            claudeapp and
            has_claude_app() and
            click.confirm("Register with Claude.app?", default=True)
        ):
            update_claude_config(name, project_path)
            
        click.echo(f"✅ Created project {name} in {project_path}")
        
    except TemplateError as e:
        click.echo(f"❌ Template error: {e}", err=True)
        sys.exit(EXIT_TEMPLATE_ERROR)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(EXIT_RUNTIME_ERROR)

@cli.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.option('--port', type=int, default=8000, help="Server port")
@click.option('--host', type=str, default="127.0.0.1", help="Server host")
def start(path: Path, port: int, host: str) -> None:
    """Start an MCP server."""
    try:
        # Load project
        pyproject = load_project(path)
        name = pyproject.metadata.name
        
        # Create and start server
        config = ServerConfig(
            name=name,
            port=port,
            host=host
        )
        
        server = ServerManager(path, name, config)
        server.start()
        
    except Exception as e:
        click.echo(f"❌ Failed to start server: {e}", err=True)
        sys.exit(EXIT_RUNTIME_ERROR)

@cli.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
def stop(path: Path) -> None:
    """Stop a running MCP server."""
    try:
        pyproject = load_project(path)
        name = pyproject.metadata.name
        
        server = ServerManager(path, name)
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
        pyproject = load_project(path)
        name = pyproject.metadata.name
        
        server = ServerManager(path, name)
        status = server.get_status()
        
        click.echo(f"Server: {name}")
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
