"""Main CLI entry point.

File: create_mcp_server/cli/main.py
"""

from pathlib import Path

import click

# from create_mcp_server.cli.prompts import prompt_for_project_details  # Removed: Using click options instead
from create_mcp_server.core.project import create_project


@click.group()
def main():  # Changed from cli to main
    """Create and manage MCP servers."""
    pass  # Use pass instead of an empty docstring


@main.command()  # Use @main.command, since the group is now named 'main'
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=False, file_okay=False, dir_okay=True, writable=True, path_type=Path),
    default=Path("."),
    help="Base directory. Defaults to current directory.",
)
@click.option("--name", "-n", type=str, prompt=True, help="Project name.")  # Make name required, with prompt
@click.option("--version", "-v", type=str, default="0.1.0", help="Project version.")
@click.option("--description", "-d", type=str, default="", help="Project description.")
def init(path: Path, name: str, version: str, description: str):  # Added type hints
    """Create a new MCP server project."""
    # project_details = prompt_for_project_details( # Removed prompt_for_project_details
    #     path, name, version, description
    # )
    # create_project(**project_details)
    create_project(path, name, version, description)  # Call create_project directly


if __name__ == "__main__":
    main()