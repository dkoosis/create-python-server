"""User interaction functions for create_mcp_server.

This module provides a clean interface for user interaction,
separating prompt logic from command handlers.

File: create_mcp_server/cli/prompts.py
"""

from pathlib import Path
from typing import Optional, Tuple

import click

from ..server.config import LogLevel, ServerConfig
from ..utils.validation import check_package_name, check_version


def prompt_for_project_details(
    path: Optional[Path],
    name: Optional[str],
    version: Optional[str],
    description: Optional[str]
) -> dict:
    """Prompt for project details if not provided."""
    if name is None:
        name = click.prompt("Project name", type=str)
        
    if not name:
        raise click.UsageError("Project name is required")
        
    is_valid, error = check_package_name(name)
    if not is_valid:
        raise click.UsageError(error)
        
    if description is None:
        description = click.prompt(
            "Project description",
            type=str,
            default="An MCP server"
        )
        
    if version is None:
        version = click.prompt(
            "Project version",
            type=str,
            default="0.1.0"
        )
        
    if path is None:
        path = Path.cwd() / name
        
    return {
        "path": path,
        "name": name,
        "version": version,
        "description": description
    }

def prompt_project_name(default: Optional[str] = None) -> str:
    """Prompt for and validate project name.
    
    Args:
        default: Optional default name to suggest
        
    Returns:
        Validated project name
        
    Raises:
        click.Abort: If user cancels input
    """
    while True:
        name = click.prompt(
            "Project name",
            type=str,
            default=default,
            show_default=bool(default)
        )
        
        is_valid, error = check_package_name(name)
        if is_valid:
            return name
            
        click.echo(f"❌ {error}", err=True)
        if not click.confirm("Try again?", default=True):
            raise click.Abort()

def prompt_project_version(default: str = "0.1.0") -> str:
    """Prompt for and validate project version.
    
    Args:
        default: Default version to suggest
        
    Returns:
        Validated version string
        
    Raises:
        click.Abort: If user cancels input
    """
    while True:
        version = click.prompt(
            "Project version",
            type=str,
            default=default,
            show_default=True
        )
        
        is_valid, error = check_version(version)
        if is_valid:
            return version
            
        click.echo(f"❌ {error}", err=True)
        if not click.confirm("Try again?", default=True):
            raise click.Abort()

def prompt_project_path(
    name: str,
    default: Optional[Path] = None
) -> Path:
    """Prompt for and validate project directory path.
    
    Args:
        name: Project name (used for default path)
        default: Optional default path to suggest
        
    Returns:
        Validated Path object
        
    Raises:
        click.Abort: If user cancels input
    """
    if default is None:
        default = Path.cwd() / name
        
    while True:
        path_str = click.prompt(
            "Project directory",
            type=str,
            default=str(default),
            show_default=True
        )
        path = Path(path_str).resolve()
        
        if path.exists() and not click.confirm(
            f"{path} already exists. Use anyway?",
            default=False
        ):
            continue
            
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        except Exception as e:
            click.echo(f"❌ Invalid path: {e}", err=True)
            if not click.confirm("Try again?", default=True):
                raise click.Abort()

def prompt_server_config(
    name: str,
    version: str,
    description: Optional[str] = None
) -> ServerConfig:
    """Prompt for server configuration options.
    
    Args:
        name: Project name
        version: Project version
        description: Optional project description
        
    Returns:
        Populated ServerConfig object
        
    Raises:
        click.Abort: If user cancels input
    """
    if description is None:
        description = click.prompt(
            "Project description",
            type=str,
            default="An MCP server",
            show_default=True
        )
        
    # Network settings
    host = click.prompt(
        "Server host",
        type=str,
        default="127.0.0.1",
        show_default=True
    )
    
    while True:
        try:
            port = click.prompt(
                "Server port",
                type=int,
                default=8000,
                show_default=True
            )
            if 1 <= port <= 65535:
                break
            click.echo("❌ Port must be between 1 and 65535", err=True)
        except click.Abort:
            raise
        except Exception:
            click.echo("❌ Invalid port number", err=True)
            
    # Logging settings    
    log_levels = [level.value for level in LogLevel]
    log_level = click.prompt(
        "Log level",
        type=click.Choice(log_levels, case_sensitive=False),
        default="info",
        show_default=True
    )
    
    return ServerConfig(
        name=name,
        version=version,
        description=description,
        host=host,
        port=port,
        log_level=LogLevel.from_string(log_level)
    )

def confirm_project_creation(path: Path, config: ServerConfig) -> bool:
    """Show project summary and confirm creation.
    
    Args:
        path: Project directory path
        config: Server configuration
        
    Returns:
        True if user confirms, False otherwise
    """
    click.echo("\nProject Summary:")
    click.echo(f"  Name: {config.name}")
    click.echo(f"  Version: {config.version}")
    click.echo(f"  Description: {config.description}")
    click.echo(f"  Directory: {path}")
    click.echo(f"  Server: {config.host}:{config.port}")
    click.echo(f"  Log Level: {config.log_level.value}")
    
    return click.confirm("\nCreate project?", default=True)

def confirm_server_start(config: ServerConfig) -> bool:
    """Confirm server startup settings.
    
    Args:
        config: Server configuration
        
    Returns:
        True if user confirms, False otherwise
    """
    click.echo("\nServer Settings:")
    click.echo(f"  Name: {config.name}")
    click.echo(f"  Host: {config.host}")
    click.echo(f"  Port: {config.port}")
    click.echo(f"  Log Level: {config.log_level.value}")
    
    return click.confirm("\nStart server?", default=True)