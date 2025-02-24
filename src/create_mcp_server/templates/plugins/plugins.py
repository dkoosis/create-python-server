"""Base classes and interfaces for the MCP server plugin system.

This module provides the core abstractions for extending server functionality
through plugins. It follows Unix philosophy principles:
- Each plugin does one thing well
- Plugins communicate through well-defined interfaces
- Plugins can be composed to create more complex functionality

Key concepts:
- PluginInterface: Protocol defining the plugin API
- PluginManager: Handles plugin discovery, loading, and lifecycle
- ResourceProvider: Interface for providing data resources
- ToolProvider: Interface for providing tools/operations
"""

import abc
import asyncio
import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Set, Type

from .core import ResourceInfo, ResourceProvider, Tool, ServerError

logger = logging.getLogger(__name__)

class PluginError(ServerError):
    """Base exception for plugin-related errors."""
    pass

class PluginInterface(Protocol):
    """Protocol defining the plugin interface.
    
    All plugins must implement this interface to be loadable by the server.
    The interface is intentionally minimal to make it easy to create new plugins.
    """
    
    @property
    def name(self) -> str:
        """Get the plugin's unique identifier."""
        ...
        
    @property
    def version(self) -> str:
        """Get the plugin's version."""
        ...
        
    async def setup(self) -> None:
        """Initialize plugin resources and configuration."""
        ...
        
    async def start(self) -> None:
        """Start plugin operation."""
        ...
        
    async def stop(self) -> None:
        """Stop plugin operation and cleanup resources."""
        ...
        
    def get_resource_providers(self) -> List[ResourceProvider]:
        """Get resource providers implemented by this plugin."""
        ...
        
    def get_tools(self) -> List[Tool]:
        """Get tools implemented by this plugin."""
        ...

@dataclass
class PluginMetadata:
    """Plugin metadata for discovery and management."""
    name: str
    version: str
    path: Path
    module_name: str
    plugin_class: str
    description: Optional[str] = None
    author: Optional[str] = None
    dependencies: Set[str] = None

class PluginManager:
    """Manages plugin lifecycle and dependencies.
    
    This class handles:
    - Plugin discovery and loading
    - Dependency resolution
    - Plugin lifecycle (setup/start/stop)
    - Resource and tool registration
    """
    
    def __init__(self, plugin_dir: Path):
        """Initialize plugin manager.
        
        Args:
            plugin_dir: Directory containing plugin modules
        """
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, PluginInterface] = {}
        self._running = False
        
    async def discover_plugins(self) -> List[PluginMetadata]:
        """Discover available plugins in the plugin directory.
        
        Returns:
            List of plugin metadata objects
            
        This scans the plugin directory for Python modules and looks for
        plugin implementation classes that provide the PluginInterface.
        """
        metadata = []
        
        for plugin_file in self.plugin_dir.glob("*.py"):
            if plugin_file.name.startswith("_"):
                continue
                
            try:
                # Load module
                spec = importlib.util.spec_from_file_location(
                    plugin_file.stem, plugin_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Find plugin class
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        attr_name.endswith("Plugin") and
                        issubclass(attr, PluginInterface)):
                        
                        metadata.append(PluginMetadata(
                            name=attr.name,
                            version=attr.version,
                            path=plugin_file,
                            module_name=plugin_file.stem,
                            plugin_class=attr_name
                        ))
                        
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_file}: {e}")
                
        return metadata
        
    async def load_plugin(self, metadata: PluginMetadata) -> None:
        """Load and initialize a plugin.
        
        Args:
            metadata: Plugin metadata from discovery
            
        Raises:
            PluginError: If plugin cannot be loaded
        """
        try:
            # Import module
            module = importlib.import_module(metadata.module_name)
            plugin_class = getattr(module, metadata.plugin_class)
            
            # Create plugin instance
            plugin = plugin_class()
            
            # Initialize plugin
            await plugin.setup()
            self.plugins[metadata.name] = plugin
            
            logger.info(f"Loaded plugin: {metadata.name} v{metadata.version}")
            
        except Exception as e:
            raise PluginError(f"Failed to load plugin {metadata.name}: {e}")
            
    async def start_plugins(self) -> None:
        """Start all loaded plugins."""
        if self._running:
            return
            
        for name, plugin in self.plugins.items():
            try:
                await plugin.start()
            except Exception as e:
                logger.error(f"Failed to start plugin {name}: {e}")
                
        self._running = True
        
    async def stop_plugins(self) -> None:
        """Stop all running plugins."""
        if not self._running:
            return
            
        for name, plugin in self.plugins.items():
            try:
                await plugin.stop()
            except Exception as e:
                logger.error(f"Failed to stop plugin {name}: {e}")
                
        self._running = False
        
    def get_resource_providers(self) -> List[ResourceProvider]:
        """Get all resource providers from loaded plugins."""
        providers = []
        for plugin in self.plugins.values():
            providers.extend(plugin.get_resource_providers())
        return providers
        
    def get_tools(self) -> List[Tool]:
        """Get all tools from loaded plugins."""
        tools = []
        for plugin in self.plugins.values():
            tools.extend(plugin.get_tools())
        return tools

class BasePlugin(PluginInterface):
    """Base implementation of the plugin interface.
    
    This provides common functionality and default implementations
    to make it easier to create new plugins.
    """
    
    name = "base"
    version = "0.1.0"
    
    def __init__(self):
        self._running = False
        self._tasks: List[asyncio.Task] = []
        
    async def setup(self) -> None:
        """Initialize plugin. Override in subclasses."""
        pass
        
    async def start(self) -> None:
        """Start plugin operation."""
        self._running = True
        
    async def stop(self) -> None:
        """Stop plugin operation."""
        self._running = False
        
        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        
    def get_resource_providers(self) -> List[ResourceProvider]:
        """Get plugin's resource providers."""
        return []
        
    def get_tools(self) -> List[Tool]:
        """Get plugin's tools."""
        return []
        
    def create_task(self, coro) -> asyncio.Task:
        """Create a managed background task.
        
        The task will be automatically cancelled when the plugin stops.
        """
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        return task
