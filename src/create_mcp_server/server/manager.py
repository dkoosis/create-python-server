"""Server lifecycle management.

This module handles the full server lifecycle including:
- Server startup and shutdown
- Health monitoring
- Process supervision
- Resource tracking
- Graceful shutdown

File: create_mcp_server/server/manager.py
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Set

import aiohttp
import psutil
from aiohttp import ClientError, ClientTimeout

from .config import ServerConfig
from ..utils.process import (
    ProcessError,
    TimeoutError,
    run_background_process,
    kill_process,
    wait_for_process
)

logger = logging.getLogger(__name__)

# Constants
HEALTH_CHECK_INTERVAL = 30  # seconds
STATUS_CHECK_INTERVAL = 60  # seconds
STARTUP_TIMEOUT = 30       # seconds
SHUTDOWN_TIMEOUT = 5       # seconds
HEALTH_CHECK_TIMEOUT = 5   # seconds
MAX_MEMORY_MB = 500       # Maximum memory usage in MB
MAX_CPU_PERCENT = 80      # Maximum CPU usage percent

class ServerError(Exception):
    """Base exception for server operations."""
    pass

class ServerStartError(ServerError):
    """Raised when server fails to start."""
    pass

class ServerStopError(ServerError):
    """Raised when server fails to stop."""
    pass

class HealthCheckError(ServerError):
    """Raised when health check fails."""
    pass

@dataclass
class ServerStatus:
    """Server status information."""
    running: bool
    pid: Optional[int]
    start_time: Optional[datetime]
    uptime: Optional[timedelta]
    memory_usage: Optional[float]  # In MB
    cpu_percent: Optional[float]
    port: int
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert status to dictionary."""
        return {
            "running": self.running,
            "pid": self.pid,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime": str(self.uptime) if self.uptime else None,
            "memory_usage": round(self.memory_usage, 1) if self.memory_usage else None,
            "cpu_percent": round(self.cpu_percent, 1) if self.cpu_percent else None,
            "port": self.port,
            "error": self.error
        }

class ServerManager:
    """Manages MCP server lifecycle."""
    
    def __init__(
        self,
        path: Path,
        name: str,
        config: Optional[ServerConfig] = None
    ):
        """Initialize server manager.
        
        Args:
            path: Path to server installation
            name: Server name
            config: Optional server configuration
        """
        self.path = path
        self.name = name
        self.config = config or ServerConfig(name=name)
        self.process: Optional[subprocess.Popen] = None
        
        # Background tasks
        self._health_check_task: Optional[asyncio.Task] = None
        self._status_monitor_task: Optional[asyncio.Task] = None
        
        # Track child processes
        self._child_processes: Set[psutil.Process] = set()
        
        # Setup signal handlers
        self._setup_signal_handlers()

    def __enter__(self) -> 'ServerManager':
        """Context manager entry."""
        return self

    async def __aenter__(self) -> 'ServerManager':
        """Async context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle termination signals."""
        logger.info(f"Received signal {signum}")
        asyncio.create_task(self.stop())

    async def start(self) -> None:
        """Start the server.
        
        Raises:
            ServerStartError: If server fails to start
        """
        if self.process and self.process.poll() is None:
            logger.warning("Server is already running")
            return

        # Check if port is available
        if not await self._is_port_available(self.config.port):
            raise ServerStartError(f"Port {self.config.port} is already in use")

        try:
            # Prepare environment
            env = os.environ.copy()
            env.update({
                "MCP_SERVER_PORT": str(self.config.port),
                "MCP_SERVER_HOST": self.config.host,
                "MCP_LOG_LEVEL": self.config.log_level.value,
            })

            # Start server process
            self.process = run_background_process(
                ["uv", "run", "uvicorn",
                 f"{self.name}.server:app",
                 "--host", self.config.host,
                 "--port", str(self.config.port),
                 "--reload" if self.config.reload else "",
                 "--log-level", self.config.log_level.value.lower()],
                cwd=self.path,
                env=env
            )
            
            logger.info(
                f"Starting server {self.name} on "
                f"{self.config.host}:{self.config.port} "
                f"(PID: {self.process.pid})"
            )
            
            # Wait for server to start
            await self._wait_for_startup()
            
            # Start monitoring tasks
            self._start_monitoring()
            
        except Exception as e:
            await self.stop()  # Cleanup on failure
            raise ServerStartError(f"Failed to start server: {e}")

    async def stop(self) -> None:
        """Stop the server gracefully."""
        if not self.process:
            return

        logger.info(f"Stopping server {self.name}")
        
        # Stop monitoring tasks
        self._stop_monitoring()

        try:
            # Stop child processes first
            for proc in self._child_processes:
                try:
                    proc.terminate()
                except psutil.NoSuchProcess:
                    pass
                    
            # Wait for child processes
            psutil.wait_procs(
                list(self._child_processes),
                timeout=SHUTDOWN_TIMEOUT
            )
            
            # Stop main process
            kill_process(self.process, timeout=SHUTDOWN_TIMEOUT)
                
        except Exception as e:
            raise ServerStopError(f"Failed to stop server: {e}")
        finally:
            self.process = None
            self._child_processes.clear()

    async def restart(self) -> None:
        """Restart the server gracefully."""
        await self.stop()
        await self.start()

    async def get_status(self) -> ServerStatus:
        """Get current server status.
        
        Returns:
            ServerStatus object with current metrics
        """
        if not self.process or self.process.poll() is not None:
            return ServerStatus(
                running=False,
                pid=None,
                start_time=None,
                uptime=None,
                memory_usage=None,
                cpu_percent=None,
                port=self.config.port
            )

        try:
            proc = psutil.Process(self.process.pid)
            start_time = datetime.fromtimestamp(proc.create_time())
            
            return ServerStatus(
                running=True,
                pid=self.process.pid,
                start_time=start_time,
                uptime=datetime.now() - start_time,
                memory_usage=proc.memory_info().rss / 1024 / 1024,
                cpu_percent=proc.cpu_percent(),
                port=self.config.port
            )
            
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return ServerStatus(
                running=False,
                pid=self.process.pid,
                start_time=None,
                uptime=None,
                memory_usage=None,
                cpu_percent=None,
                port=self.config.port,
                error=str(e)
            )

    async def _is_port_available(self, port: int) -> bool:
        """Check if a port is available.
        
        Args:
            port: Port number to check
            
        Returns:
            True if port is available, False if in use
        """
        timeout = ClientTimeout(total=1)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"http://localhost:{port}/health"
                ) as _:
                    return False  # Port is in use
        except:
            return True

    async def _wait_for_startup(self) -> None:
        """Wait for server to start and verify it's running.
        
        Raises:
            ServerStartError: If server fails to start within timeout
        """
        start_time = time.time()
        last_error = None
        health_check_url = f"http://{self.config.host}:{self.config.port}/health"
        
        timeout = ClientTimeout(total=HEALTH_CHECK_TIMEOUT)
        
        while (time.time() - start_time) < STARTUP_TIMEOUT:
            # Check if process died
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                raise ServerStartError(
                    f"Server process terminated unexpectedly:\n"
                    f"stdout: {stdout}\nstderr: {stderr}"
                )

            # Check health endpoint
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(health_check_url) as response:
                        if response.status == 200:
                            logger.info(f"Server {self.name} started successfully")
                            return
                        last_error = f"Health check failed with status {response.status}"
            except Exception as e:
                last_error = str(e)

            await asyncio.sleep(0.5)

        raise ServerStartError(
            f"Server failed to start within {STARTUP_TIMEOUT} seconds: {last_error}"
        )

    def _start_monitoring(self) -> None:
        """Start background monitoring tasks."""
        if not self._health_check_task:
            self._health_check_task = asyncio.create_task(
                self._health_check_loop()
            )
        if not self._status_monitor_task:
            self._status_monitor_task = asyncio.create_task(
                self._status_monitor_loop()
            )

    def _stop_monitoring(self) -> None:
        """Stop background monitoring tasks."""
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None
        if self._status_monitor_task:
            self._status_monitor_task.cancel()
            self._status_monitor_task = None

    async def _health_check_loop(self) -> None:
        """Periodic health check loop."""
        health_check_url = f"http://{self.config.host}:{self.config.port}/health"
        timeout = ClientTimeout(total=HEALTH_CHECK_TIMEOUT)
        
        while True:
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(health_check_url) as response:
                        if response.status != 200:
                            logger.warning(
                                f"Health check failed: {response.status}"
                            )
                            await self._handle_health_failure("Bad status")
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                await self._handle_health_failure(str(e))
            
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def _status_monitor_loop(self) -> None:
        """Periodic status monitoring loop."""
        while True:
            try:
                status = await self.get_status()
                
                # Check memory usage
                if status.memory_usage and status.memory_usage > MAX_MEMORY_MB:
                    logger.warning(
                        f"High memory usage: {status.memory_usage:.1f}MB"
                    )
                    
                # Check CPU usage
                if status.cpu_percent and status.cpu_percent > MAX_CPU_PERCENT:
                    logger.warning(
                        f"High CPU usage: {status.cpu_percent:.1f}%"
                    )
                    
            except Exception as e:
                logger.error(f"Status monitoring failed: {e}")
            
            await asyncio.sleep(STATUS_CHECK_INTERVAL)

    async def _handle_health_failure(self, reason: str) -> None:
        """Handle health check failure.
        
        Args:
            reason: Failure reason
        """
        logger.error(f"Health check failed: {reason}")
        
        # Could implement recovery logic here, e.g.:
        # - Restart server
        # - Notify monitoring system
        # - Write to error log
        # For now, just log the error
        pass