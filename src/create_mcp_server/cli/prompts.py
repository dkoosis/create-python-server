"""User interaction functions for create_mcp_server.

This module provides a clean interface for user interaction,
separating prompt logic from command handlers. It handles:
- User input validation
- Default value handling
- Error reporting
- Type conversion
- Help text
- Confirmation prompts

File: create_mcp_server/cli/prompts.py
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, Union, cast

import click

from ..server.config import LogLevel, ServerConfig
from ..utils.validation import (
    ValidationResult,
    check_package_name,
    check_version,
    check_project_path,
    validate_description,
    validate_url,
    validate_email
)

logger = logging.getLogger(__name__)

T = TypeVar('T')

@dataclass
class PromptOptions:
    """Options for customizing prompts."""
    prompt_text: str
    help_text: Optional[str] = None
    default: Optional[Any] = None
    show_default: bool = True
    required: bool = True
    confirmation: bool = False
    abort_on_error: bool = True

def prompt_with_validation(
    options: PromptOptions,
    validator: Callable[[Any], ValidationResult],
    value_type: type = str
) -> Any:
    """Generic prompt function with validation.

    Args:
        options: Prompt configuration options
        validator: Validation function
        value_type: Expected value type

    Returns:
        Validated input value

    Raises:
        click.Abort: If user cancels or validation fails with abort_on_error
    """
    while True:
        # Show help text if available
        if options.help_text:
            click.echo(f"\n{options.help_text}")

        try:
            # Handle prompt
            value = click.prompt(
                options.prompt_text,
                type=value_type,
                default=options.default,
                show_default=options.show_default
            )

            # Handle empty input
            if not value and options.required:
                click.echo("❌ This field is required", err=True)
                continue

            # Validate input
            result = validator(value)
            if not result.is_valid:
                click.echo(f"❌ {result.message}", err=True)
                if options.abort_on_error:
                    raise click.Abort()
                if not click.confirm("Try again?", default=True):
                    raise click.Abort()
                continue

            # Handle confirmation
            if options.confirmation:
                if not click.confirm("Is this correct?", default=True):
                    continue

            return value

        except click.exceptions.Abort:
            raise
        except Exception as e:
            click.echo(f"❌ Invalid input: {e}", err=True)
            if options.abort_on_error:
                raise click.Abort()
            if not click.confirm("Try again?", default=True):
                raise click.Abort()

def prompt_project_name(default: Optional[str] = None) -> str:
    """Prompt for and validate project name.

    Args:
        default: Optional default name to suggest

    Returns:
        Validated project name

    Raises:
        click.Abort: If user cancels input
    """
    options = PromptOptions(
        prompt_text="Project name",
        help_text="Enter a name for your MCP server project.\n"
                 "Use only letters, numbers, hyphens, and underscores.",
        default=default,
        show_default=bool(default),
        required=True,
        confirmation=True
    )
    
    return prompt_with_validation(options, check_package_name)

def prompt_project_version(default: str = "0.1.0") -> str:
    """Prompt for and validate project version.

    Args:
        default: Default version to suggest

    Returns:
        Validated version string

    Raises:
        click.Abort: If user cancels input
    """
    options = PromptOptions(
        prompt_text="Project version",
        help_text="Enter the initial version number.\n"
                 "Use semantic versioning (e.g., 1.0.0).",
        default=default,
        required=True
    )
    
    return prompt_with_validation(options, check_version)

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
        
    options = PromptOptions(
        prompt_text="Project directory",
        help_text="Enter the directory where the project will be created.",
        default=str(default),
        required=True,
        confirmation=True
    )
    
    return Path(prompt_with_validation(
        options,
        lambda p: check_project_path(Path(p))
    ))

def prompt_description(default: str = "An MCP server") -> str:
    """Prompt for project description.

    Args:
        default: Default description

    Returns:
        Validated description

    Raises:
        click.Abort: If user cancels input
    """
    options = PromptOptions(
        prompt_text="Project description",
        help_text="Enter a brief description of your MCP server.",
        default=default,
        required=False
    )
    
    return prompt_with_validation(options, validate_description)

def prompt_for_project_details(
    path: Optional[Path],
    name: Optional[str],
    version: Optional[str],
    description: Optional[str]
) -> Dict[str, Any]:
    """Prompt for missing project details.

    Args:
        path: Project directory (optional)
        name: Project name (optional)
        version: Project version (optional)
        description: Project description (optional)

    Returns:
        Dictionary of project details

    Raises:
        click.Abort: If user cancels any prompt
    """
    details = {}

    # Get project name
    if name is None:
        details['name'] = prompt_project_name()
    else:
        result = check_package_name(name)
        if not result.is_valid:
            raise click.UsageError(result.message)
        details['name'] = name

    # Get project path
    if path is None:
        details['path'] = prompt_project_path(details.get('name', name))
    else:
        result = check_project_path(path)
        if not result.is_valid:
            raise click.UsageError(result.message)
        details['path'] = path

    # Get version
    if version is None:
        details['version'] = prompt_project_version()
    else:
        result = check_version(version)
        if not result.is_valid:
            raise click.UsageError(result.message)
        details['version'] = version

    # Get description
    if description is None:
        details['description'] = prompt_description()
    else:
        result = validate_description(description)
        if not result.is_valid:
            raise click.UsageError(result.message)
        details['description'] = description

    return details

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
        description = prompt_description()

    # Network settings
    host_options = PromptOptions(
        prompt_text="Server host",
        help_text="Enter the host address to bind to.",
        default="127.0.0.1"
    )
    host = prompt_with_validation(
        host_options,
        lambda h: ValidationResult(True, "") if h else ValidationResult(False, "Host is required")
    )

    port_options = PromptOptions(
        prompt_text="Server port",
        help_text="Enter the port number (1-65535).",
        default=8000
    )
    port = prompt_with_validation(
        port_options,
        lambda p: ValidationResult(
            True, ""
        ) if 1 <= int(p) <= 65535 else ValidationResult(
            False, "Port must be between 1 and 65535"
        ),
        value_type=int
    )

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