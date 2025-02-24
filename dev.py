#!/usr/bin/env python3
"""Development workflow script.

File: /Users/davidkoosis/projects/create_mcp_server/dev.py

Provides commands for common development tasks using uv.
"""

import subprocess
import sys
from pathlib import Path

def run_uv(args, **kwargs):
    """Run a uv command."""
    cmd = ["uv"] + args
    return subprocess.run(cmd, **kwargs, check=True)

def setup():
    """Set up development environment."""
    run_uv(["venv"])
    run_uv(["pip", "install", "--editable", ".[dev]"])

def test():
    """Run tests."""
    run_uv(["python", "-m", "pytest"])

def lint():
    """Run linters."""
    run_uv(["python", "-m", "ruff", "check", "."])
    run_uv(["python", "-m", "black", "--check", "."])

if __name__ == "__main__":
    commands = {
        "setup": setup,
        "test": test,
        "lint": lint,
    }
    
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print(f"Usage: {sys.argv[0]} [{' | '.join(commands.keys())}]")
        sys.exit(1)
        
    commands[sys.argv[1]]()
