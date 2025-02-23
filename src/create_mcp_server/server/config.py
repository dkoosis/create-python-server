"""Server configuration management.

This module handles server configuration through environment variables
and settings files. It implements a layered configuration approach:

1. Default values
2. Environment variables
3. Config file overrides
4. Command line arguments

File: create_mcp_server/server/config.py
"""

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

class LogLevel(str, Enum):
    """Valid logging levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @classmethod
    def from_string(cls, level: str) -> 'LogLevel':
        """Convert string to LogLevel, defaulting to INFO for invalid values."""
        try:
            return cls(level.lower())
        except ValueError:
            logger.warning(f"Invalid log level '{level}', defaulting to INFO")
            return cls.INFO

    def to_python_level(self) -> int:
        """Convert to Python logging level."""
        return getattr(logging, self.value.upper())

@dataclass
class ServerConfig:
    """Server configuration settings.
    
    This class manages all server settings with support for environment
    variables and config file overrides.
    """
    # Core settings
    name: str
    version: str = "0.1.0"
    description: str = "MCP Server"
    
    # Network settings
    host: str = "127.0.0.1"
    port: int = 8000
    
    # Logging settings
    log_level: LogLevel = LogLevel.INFO
    log_file: Optional[str] = None
    
    # Plugin settings
    plugin_dir: Optional[Path] = None
    enabled_plugins: List[str] = field(default_factory=list)
    plugin_config: Dict[str, Any] = field(default_factory=dict)
    
    # Security settings
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    api_keys: Dict[str, str] = field(default_factory=dict)
    
    # Resource settings
    resource_paths: List[Path] = field(default_factory=list)
    max_resource_size: int = 10 * 1024 * 1024  # 10MB
    
    # Development settings
    dev_mode: bool = False
    reload: bool = False
    
    @classmethod
    def from_env(cls, **kwargs) -> 'ServerConfig':
        """Create config from environment variables.
        
        Environment variables take the form MCP_*, e.g.:
        - MCP_HOST: Server host
        - MCP_PORT: Server port
        - MCP_LOG_LEVEL: Logging level
        """
        # Start with any provided kwargs
        config_dict = {k: v for k, v in kwargs.items() if v is not None}
        
        # Core settings
        config_dict["name"] = os.getenv("MCP_NAME", config_dict.get("name"))
        config_dict["version"] = os.getenv("MCP_VERSION", config_dict.get("version"))
        config_dict["description"] = os.getenv("MCP_DESCRIPTION", config_dict.get("description"))
        
        # Network settings
        config_dict["host"] = os.getenv("MCP_HOST", config_dict.get("host", "127.0.0.1"))
        config_dict["port"] = int(os.getenv("MCP_PORT", config_dict.get("port", 8000)))
        
        # Logging settings
        log_level = os.getenv("MCP_LOG_LEVEL", config_dict.get("log_level", "info"))
        config_dict["log_level"] = LogLevel.from_string(log_level)
        config_dict["log_file"] = os.getenv("MCP_LOG_FILE", config_dict.get("log_file"))
        
        # Plugin settings
        plugin_dir = os.getenv("MCP_PLUGIN_DIR")
        if plugin_dir:
            config_dict["plugin_dir"] = Path(plugin_dir)
            
        plugins = os.getenv("MCP_ENABLED_PLUGINS")
        if plugins:
            config_dict["enabled_plugins"] = plugins.split(",")
            
        # Security settings
        origins = os.getenv("MCP_ALLOWED_ORIGINS")
        if origins:
            config_dict["allowed_origins"] = origins.split(",")
            
        # Resource settings
        paths = os.getenv("MCP_RESOURCE_PATHS")
        if paths:
            config_dict["resource_paths"] = [Path(p) for p in paths.split(",")]
            
        max_size = os.getenv("MCP_MAX_RESOURCE_SIZE")
        if max_size:
            config_dict["max_resource_size"] = int(max_size)
            
        # Development settings
        config_dict["dev_mode"] = os.getenv("MCP_DEV_MODE", "").lower() == "true"
        config_dict["reload"] = os.getenv("MCP_RELOAD", "").lower() == "true"
        
        return cls(**config_dict)

    @classmethod
    def from_file(cls, path: Path) -> 'ServerConfig':
        """Load configuration from a JSON file."""
        try:
            config_dict = json.loads(path.read_text())
            return cls(**config_dict)
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            return cls()

    def to_file(self, path: Path) -> None:
        """Save configuration to a JSON file."""
        try:
            # Convert to dict, handling Path objects
            config_dict = asdict(self)
            config_dict["resource_paths"] = [
                str(p) for p in self.resource_paths
            ]
            config_dict["log_level"] = self.log_level.value
            
            # Write using atomic utility
            atomic_write(path, json.dumps(config_dict, indent=2))
                
        except Exception as e:
            logger.error(f"Failed to save config to {path}: {e}")

    def setup_logging(self) -> None:
        """Configure logging based on settings."""
        log_config = {
            'version': 1,
            'formatters': {
                'default': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'default',
                    'level': self.log_level.to_python_level()
                }
            },
            'root': {
                'level': self.log_level.to_python_level(),
                'handlers': ['console']
            }
        }
        
        # Add file handler if configured
        if self.log_file:
            log_config['handlers']['file'] = {
                'class': 'logging.FileHandler',
                'filename': self.log_file,
                'formatter': 'default',
                'level': self.log_level.to_python_level()
            }
            log_config['root']['handlers'].append('file')
        
        logging.config.dictConfig(log_config)

    def validate(self) -> List[str]:
        """Validate configuration settings.
        
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Basic validation
        if not self.name:
            errors.append("Server name is required")
            
        if self.port < 1 or self.port > 65535:
            errors.append(f"Invalid port number: {self.port}")
            
        # Check resource paths exist
        for path in self.resource_paths:
            if not path.exists():
                errors.append(f"Resource path does not exist: {path}")
                
        # Check plugin directory
        if self.plugin_dir and not self.plugin_dir.exists():
            errors.append(f"Plugin directory does not exist: {self.plugin_dir}")
            
        # Validate enabled plugins exist if plugin dir is set
        if self.plugin_dir and self.enabled_plugins:
            for plugin in self.enabled_plugins:
                plugin_file = self.plugin_dir / f"{plugin}.py"
                if not plugin_file.exists():
                    errors.append(f"Plugin file not found: {plugin_file}")
                    
        return errors

    def get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """Get configuration for a specific plugin."""
        return self.plugin_config.get(plugin_name, {})

    def __post_init__(self) -> None:
        """Validate and process after initialization."""
        # Convert string log level to enum if needed
        if isinstance(self.log_level, str):
            self.log_level = LogLevel.from_string(self.log_level)
            
        # Convert path strings to Path objects
        if isinstance(self.plugin_dir, str):
            self.plugin_dir = Path(self.plugin_dir)
            
        self.resource_paths = [
            Path(p) if isinstance(p, str) else p
            for p in self.resource_paths
        ]
