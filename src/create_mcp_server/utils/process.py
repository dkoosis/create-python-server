"""Process management and UV package manager utilities.

This module handles interactions with external processes, particularly
the UV package manager. It provides functions for:

- Verifying UV installation and version
- Running UV commands safely
- Managing subprocess execution and error handling
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import click
from packaging.version import Version, parse

# Constants
MIN_UV_VERSION = "0.1.10"  # Changed to a more likely minimum version
PROCESS_TIMEOUT = 300  # 5 minutes default timeout

class ProcessError(Exception):
    """Base exception for process-related errors."""
    pass

class UVNotFoundError(ProcessError):
    """Raised when UV is not installed."""
    pass

class UVVersionError(ProcessError):
    """Raised when UV version is incompatible."""
    pass

class CommandError(ProcessError):
    """Raised when a command fails."""
    def __init__(self, cmd: List[str], returncode: int, stdout: str, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        msg = f"Command '{' '.join(cmd)}' failed with exit code {returncode}"
        if stdout:
            msg += f"\nOutput: {stdout}"
        if stderr:
            msg += f"\nError: {stderr}"
        super().__init__(msg)

def check_uv_version(required_version: str = MIN_UV_VERSION) -> Optional[Version]:
    """Check if UV is installed and verify its version."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        version_str = result.stdout.strip()
        match = re.match(r"uv (\d+\.\d+\.\d+)", version_str)
        if not match:
            raise UVVersionError(f"Unable to parse UV version from: {version_str}")

        version = parse(match.group(1))
        required = parse(required_version)

        if version < required:
            raise UVVersionError(
                f"UV version {version} is older than required version {required_version}"
            )

        return version

    except FileNotFoundError:
        raise UVNotFoundError("UV package manager not found")
    except subprocess.CalledProcessError as e:
        raise ProcessError(f"Error checking UV version: {e}")

def ensure_uv_installed() -> None:
    """Ensure UV is installed at minimum version."""
    try:
        check_uv_version()
    except UVNotFoundError:
        click.echo("❌ UV package manager is not installed", err=True)
        click.echo("To install, visit: https://github.com/astral-sh/uv", err=True)
        sys.exit(1)
    except UVVersionError as e:
        click.echo(f"❌ {e}", err=True)
        click.echo("To upgrade, visit: https://github.com/astral-sh/uv", err=True)
        sys.exit(1)

def run_uv_command(
    args: List[str],
    cwd: Path,
    env: Optional[Dict[str, str]] = None,
    timeout: int = PROCESS_TIMEOUT,
    check: bool = True
) -> subprocess.CompletedProcess:
    """Run a UV command with proper error handling."""
    cmd = ["uv", *args]  # Construct the full command

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False  # We'll handle checking manually
        )

        if check and result.returncode != 0:
            raise CommandError(
                cmd=cmd,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr
            )

        return result

    except subprocess.TimeoutExpired as e:
        raise CommandError(
            cmd=cmd,
            returncode=-1,  # Use -1 for timeout
            stdout="",
            stderr=f"Command timed out after {timeout} seconds"
        ) from e

def run_background_process(
    args: List[str],
    cwd: Path,
    env: Optional[Dict[str, str]] = None
) -> subprocess.Popen:
    """Start a long-running background process."""
    try:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Quick check if process failed to start immediately
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise CommandError(
                cmd=args,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr
            )

        return process

    except Exception as e:
        raise ProcessError(f"Failed to start process: {e}")

def kill_process(process: subprocess.Popen, timeout: int = 5) -> None:
    """Safely kill a running process."""
    if process.poll() is None:  # Check if process is still running
        process.terminate()  # Try graceful termination
        try:
            process.wait(timeout=timeout)  # Wait for termination
        except subprocess.TimeoutExpired:
            process.kill()  # Force termination if it times out
            process.wait() # wait for the kill to complete