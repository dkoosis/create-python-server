"""Main CLI entry point."""
import click
from pathlib import Path
from create_mcp_server.core.project import create_project
from create_mcp_server.cli.prompts import prompt_for_project_details

@click.group()
def cli():
    """Create and manage MCP servers."""
    pass

@cli.command()
@click.option("--path", type=click.Path(path_type=Path))
@click.option("--name", type=str)
@click.option("--version", type=str)
@click.option("--description", type=str)
def create(path, name, version, description):
    """Create a new MCP server project."""
    project_details = prompt_for_project_details(path, name, version, description)
    create_project(**project_details)

def main():
    """Main entry point."""
    return cli()
