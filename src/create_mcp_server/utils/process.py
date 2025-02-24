"""Process management and UV package manager utilities.

This module handles interactions with external processes, particularly
the UV package manager. It provides functions for:

- Verifying UV installation and version
- Running UV commands safely
- Managing subprocess execution and error handling
- Handling process timeouts and cleanup

File: create_mcp_server/utils/process.py
"""

import logging
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Union

import click
from packaging.version import Version, parse

logger = logging.getLogger(__name__)

# Constants
MIN_UV_VERSION = "0.1.10"
PROCESS_TIMEOUT = 300  # 5 minutes default timeout
STARTUP_TIMEOUT = 30   # 30 seconds for startup checks
SHUTDOWN_TIMEOUT = 5   # 5 seconds for graceful shutdown

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
    def __init__(
        self, 
        cmd: List[str], 
        returncode: int, 
        stdout: str, 
        stderr: str
    ):
        """Initialize with command details.
        
        Args:
            cmd: Command that was executed
            returncode: Process return code
            stdout: Process stdout output
            stderr: Process stderr output
        """
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

class TimeoutError(ProcessError):
    """Raised when a process times out."""
    pass

@contextmanager
def process_cleanup() -> Iterator[None]:
    """Context manager for cleaning up child processes.
    
    Ensures child processes are terminated on exit.
    """
    try:
        yield
    finally:
        # Clean up any remaining child processes
        if sys.platform != "win32":
            try:
                os.killpg(os.getpgid(0), signal.SIGTERM)
            except ProcessLookupError:
                pass

def check_uv_version(required_version: str = MIN_UV_VERSION) -> Optional[Version]:
    """Check if UV is installed and verify its version.
    
    Args:
        required_version: Minimum required UV version
        
    Returns:
        Installed UV version if compatible
        
    Raises:
        UVNotFoundError: If UV is not installed
        UVVersionError: If UV version is incompatible
        ProcessError: If version check fails
    """
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        version_str = result.stdout.strip()
        match = re.match(r"uv (\d+\.\d+\.\d+)", version_str)
        if not match:
            raise UVVersionError(
                f"Unable to parse UV version from: {version_str}"
            )

        version = parse(match.group(1))
        required = parse(required_version)

        if version < required:
            raise UVVersionError(
                f"UV version {version} is older than required version "
                f"{required_version}"
            )

        return version

    except FileNotFoundError:
        raise UVNotFoundError(
            "UV package manager not found. "
            "To install, visit: https://github.com/astral-sh/uv"
        )
    except subprocess.TimeoutExpired:
        raise ProcessError("Timeout checking UV version")
    except subprocess.CalledProcessError as e:
        raise ProcessError(f"Error checking UV version: {e}")

def ensure_uv_installed() -> None:
    """Ensure UV is installed at minimum version.
    
    Raises:
        SystemExit: If UV is not installed or version is incompatible
    """
    try:
        check_uv_version()
    except UVNotFoundError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)
    except UVVersionError as e:
        click.echo(f"❌ {e}", err=True)
        click.echo(
            "To upgrade, visit: https://github.com/astral-sh/uv",
            err=True
        )
        sys.exit(1)
    except ProcessError as e:
        click.echo(f"❌ Error checking UV: {e}", err=True)
        sys.exit(1)

def run_uv_command(
    args: List[str],
    cwd: Union[str, Path],
    env: Optional[Dict[str, str]] = None,
    timeout: int = PROCESS_TIMEOUT,
    check: bool = True,
    capture_output: bool = True
) -> subprocess.CompletedProcess:
    """Run a UV command with proper error handling.
    
    Args:
        args: Command arguments
        cwd: Working directory
        env: Optional environment variables
        timeout: Command timeout in seconds
        check: Whether to check return code
        capture_output: Whether to capture stdout/stderr
        
    Returns:
        CompletedProcess instance
        
    Raises:
        CommandError: If command fails and check is True
        TimeoutError: If command times out
    """
    cmd = ["uv", *args]
    
    # Set up process group for cleanup
    start_new_session = sys.platform != "win32"
    
    # Prepare environment
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    try:
        with process_cleanup():
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                env=full_env,
                capture_output=capture_output,
                text=capture_output,
                check=False,
                timeout=timeout,
                start_new_session=start_new_session
            )

        if check and result.returncode != 0:
            raise CommandError(
                cmd=cmd,
                returncode=result.returncode,
                stdout=result.stdout if capture_output else "",
                stderr=result.stderr if capture_output else ""
            )

        return result

    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
        ) from e

def run_background_process(
    args: List[str],
    cwd: Union[str, Path],
    env: Optional[Dict[str, str]] = None
) -> subprocess.Popen:
    """Start a long-running background process.
    
    Args:
        args: Command arguments
        cwd: Working directory
        env: Optional environment variables
        
    Returns:
        Popen instance for the background process
        
    Raises:
        ProcessError: If process fails to start
    """
    # Set up process group for cleanup
    start_new_session = sys.platform != "win32"
    
    # Prepare environment
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    try:
        process = subprocess.Popen(
            args,
            cwd=str(cwd),
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=start_new_session
        )

        # Quick check if process failed to start
        time.sleep(0.1)  # Short delay to check startup
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

def kill_process(
    process: subprocess.Popen,
    timeout: int = SHUTDOWN_TIMEOUT
) -> None:
    """Safely kill a running process.
    
    Args:
        process: Process to kill
        timeout: Timeout for graceful shutdown in seconds
    """
    if process.poll() is None:  # Check if process is still running
        # Try graceful termination first
        try:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Process did not terminate gracefully, forcing..."
                )
                process.kill()
                process.wait()
        except ProcessLookupError:
            pass  # Process already gone
        except Exception as e:
            logger.error(f"Error killing process: {e}")

def wait_for_process(
    process: subprocess.Popen,
    timeout: Optional[int] = None,
    check: bool = True
) -> None:
    """Wait for a process to complete.
    
    Args:
        process: Process to wait for
        timeout: Optional timeout in seconds
        check: Whether to check return code
        
    Raises:
        CommandError: If process fails and check is True
        TimeoutError: If timeout is reached
    """
    try:
        returncode = process.wait(timeout=timeout)
        if check and returncode != 0:
            stdout, stderr = process.communicate()
            raise CommandError(
                cmd=process.args,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr
            )
    except subprocess.TimeoutExpired:
        kill_process(process)
        raise TimeoutError(
            f"Process timed out after {timeout} seconds"
        )