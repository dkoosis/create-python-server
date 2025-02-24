"""
Entry point for the `create_mcp_server` package.

This file allows the package to be executed as a module using the command:

    python -m create_mcp_server

It imports and calls the `cli` function from `create_mcp_server.cli.main`,
which handles the command-line interface.
"""

from.cli.main import cli

if __name__ == "__main__":
    cli()