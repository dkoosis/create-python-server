"""Process management and UV package manager utilities.

This module handles interactions with external processes, particularly
the UV package manager. It provides functions for:

- Verifying UV installation and version
- Running UV commands safely
- Managing subprocess execution and error handling

File: create_mcp_server/utils/process.py
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import click
from packaging.version import Version, parse

# Constants
MIN_UV_VERSION = "0.4.10"
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
    """Check if UV is installed and verify its version.
    
    Args:
        required_version: Minimum required UV version
        
    Returns:
        Version object if UV meets version requirement, None otherwise
        
    Raises:
        UVNotFoundError: If UV is not installed
        UVVersionError: If UV version is incompatible
    """
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
    """Ensure UV is installed at minimum version.
    
    Raises:
        UVNotFoundError: If UV is not installed
        UVVersionError: If UV version is incompatible
    """
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
    """Run a UV command with proper error handling.
    
    Args:
        args: Command arguments to pass to UV
        cwd: Working directory for command execution
        env: Optional environment variables
        timeout: Command timeout in seconds
        check: Whether to check return code
        
    Returns:
        CompletedProcess instance
        
    Raises:
        CommandError: If command fails and check=True
        TimeoutExpired: If command exceeds timeout
    """
    cmd = ["uv", *args]
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
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
            returncode=-1,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds"
        ) from e

def run_background_process(
    args: List[str],
    cwd: Path,
    env: Optional[Dict[str, str]] = None
) -> subprocess.Popen:
    """Start a long-running background process.
    
    Args:
        args: Command arguments
        cwd: Working directory
        env: Optional environment variables
        
    Returns:
        Popen object for the running process
        
    This is useful for starting servers and other long-running processes
    that shouldn't block the main thread.
    """
    try:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Quick check if process failed to start
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
    """Safely kill a running process.
    
    Args:
        process: Popen object to terminate
        timeout: Seconds to wait for graceful termination
        
    This attempts a graceful termination first, then forces
    if the process doesn't respond.
    """
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
