"""Main entry point for create_mcp_server CLI.

File: /Users/davidkoosis/projects/create_mcp_server/src/create_mcp_server/__main__.py

This module serves as the entry point when the package is run directly with
`python -m create_mcp_server` or when installed as a console script.
"""

from .cli.commands import cli

if __name__ == '__main__':
    cli()