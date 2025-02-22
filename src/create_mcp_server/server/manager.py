"""Server lifecycle management.

This module handles server lifecycle including:
- Starting and stopping servers
- Health monitoring
- Port management
- Process supervision
"""

import asyncio
import aiohttp
import subprocess
import signal
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
import click
import sys
from dataclasses import dataclass
from .config import ServerConfig
from datetime import datetime, timedelta
import psutil

logger = logging.getLogger(__name__)

class ServerError(Exception):
    """Base exception for server operations."""
    pass

class ServerStartError(ServerError):
    """Raised when server fails to start."""
    pass

class ServerStopError(ServerError):
    """Raised when server fails to stop."""
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
    error: Optional[str] = None

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
        self._health_check_task: Optional[asyncio.Task] = None
        self._status_monitor_task: Optional[asyncio.Task] = None

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

        # Prepare environment
        env = os.environ.copy()
        env.update({
            "MCP_SERVER_PORT": str(self.config.port),
            "MCP_SERVER_HOST": self.config.host,
            "MCP_LOG_LEVEL": self.config.log_level.value,
        })

        try:
            # Start server process
            self.process = subprocess.Popen(
                ["uv", "run", self.name],
                cwd=self.path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            logger.info(f"Starting server {self.name} (PID: {self.process.pid})")
            
            # Wait for server to start
            await self._wait_for_startup()
            
            # Start monitoring tasks
            self._start_monitoring()
            
        except Exception as e:
            await self.stop()  # Cleanup on failure
            raise ServerStartError(f"Failed to start server: {e}")

    async def stop(self) -> None:
        """Stop the server gracefully.
        
        Raises:
            ServerStopError: If server cannot be stopped
        """
        if not self.process:
            return

        logger.info(f"Stopping server {self.name}")
        
        # Stop monitoring tasks
        self._stop_monitoring()

        try:
            # Try graceful shutdown first
            self.process.terminate()
            try:
                await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *[sys.executable, "-c", ""],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    ),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("Server did not stop gracefully, forcing...")
                self.process.kill()
                
            await asyncio.sleep(0.1)  # Brief pause
            
            if self.process.poll() is None:
                raise ServerStopError("Failed to stop server process")
                
        finally:
            self.process = None

    async def restart(self) -> None:
        """Restart the server."""
        await self.stop()
        await self.start()

    async def get_status(self) -> ServerStatus:
        """Get current server status."""
        if not self.process:
            return ServerStatus(
                running=False,
                pid=None,
                start_time=None,
                uptime=None,
                memory_usage=None,
                cpu_percent=None
            )

        try:
            proc = psutil.Process(self.process.pid)
            
            return ServerStatus(
                running=proc.is_running(),
                pid=proc.pid,
                start_time=datetime.fromtimestamp(proc.create_time()),
                uptime=datetime.now() - datetime.fromtimestamp(proc.create_time()),
                memory_usage=proc.memory_info().rss / 1024 / 1024,  # Convert to MB
                cpu_percent=proc.cpu_percent()
            )
        except Exception as e:
            return ServerStatus(
                running=False,
                pid=self.process.pid,
                start_time=None,
                uptime=None,
                memory_usage=None,
                cpu_percent=None,
                error=str(e)
            )

    async def _wait_for_startup(self, timeout: int = 30, check_interval: float = 0.5) -> None:
        """Wait for server to start and verify it's running.
        
        Args:
            timeout: Maximum seconds to wait
            check_interval: Seconds between health checks
            
        Raises:
            ServerStartError: If server fails to start within timeout
        """
        start_time = time.time()
        last_error = None
        
        while (time.time() - start_time) < timeout:
            # Check if process died
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                raise ServerStartError(
                    f"Server process terminated:\nstdout: {stdout}\nstderr: {stderr}"
                )

            # Check health endpoint
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"http://{self.config.host}:{self.config.port}/health",
                        timeout=1
                    ) as response:
                        if response.status == 200:
                            logger.info(f"Server {self.name} started successfully")
                            return
                        last_error = f"Health check failed with status {response.status}"
            except Exception as e:
                last_error = str(e)

            await asyncio.sleep(check_interval)

        raise ServerStartError(
            f"Server failed to start within {timeout} seconds: {last_error}"
        )

    async def _is_port_available(self, port: int) -> bool:
        """Check if a port is available."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://localhost:{port}",
                    timeout=0.1
                ) as _:
                    return False
        except:
            return True

    def _start_monitoring(self) -> None:
        """Start background monitoring tasks."""
        if not self._health_check_task:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
        if not self._status_monitor_task:
            self._status_monitor_task = asyncio.create_task(self._status_monitor_loop())

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
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"http://{self.config.host}:{self.config.port}/health"
                    ) as response:
                        if response.status != 200:
                            logger.warning(
                                f"Server health check failed: {response.status}"
                            )
            except Exception as e:
                logger.error(f"Health check failed: {e}")
            
            await asyncio.sleep(30)  # Check every 30 seconds

    async def _status_monitor_loop(self) -> None:
        """Periodic status monitoring loop."""
        while True:
            try:
                status = await self.get_status()
                if status.error:
                    logger.warning(f"Status check error: {status.error}")
                elif status.memory_usage and status.memory_usage > 500:  # 500MB
                    logger.warning(f"High memory usage: {status.memory_usage:.1f}MB")
            except Exception as e:
                logger.error(f"Status monitoring failed: {e}")
            
            await asyncio.sleep(60)  # Check every minute

def start_server(path: Path, name: str) -> None:
    """Start an MCP server from command line.
    
    Args:
        path: Path to server installation
        name: Server name
    """
    click.echo(f"\nStarting {name} server...")
    
    try:
        manager = ServerManager(path, name)
        
        # Create event loop and run server
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(manager.start())
            
            click.echo("✅ Server started successfully")
            click.echo("\nServer endpoints (default):")
            click.echo("  Health check: http://localhost:8000/health")
            click.echo("  API docs: http://localhost:8000/docs")
            
            # Handle Ctrl+C gracefully
            def signal_handler():
                click.echo("\nStopping server...")
                loop.run_until_complete(manager.stop())
                click.echo("Server stopped.")
                loop.stop()
            
            loop.add_signal_handler(signal.SIGINT, signal_handler)
            loop.run_forever()
            
        finally:
            loop.close()
            
    except Exception as e:
        click.echo(f"❌ Failed to start server: {e}", err=True)
        sys.exit(1)