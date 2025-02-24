"""Server configuration management.

This module handles server configuration through a layered approach:
1. Default values
2. Environment variables
3. Config file overrides
4. Command line arguments

Uses TypedDict for strict typing of configuration values.

File: create_mcp_server/server/config.py
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict, Union, cast

from create_mcp_server.utils.files import atomic_write
from create_mcp_server.utils.validation import validate_description, check_package_name

logger = logging.getLogger(__name__)

class ConfigError(Exception):
    """Base exception for configuration errors."""
    pass

class ValidationError(ConfigError):
    """Raised when configuration validation fails."""
    pass

class LogLevel(str, Enum):
    """Valid logging levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @classmethod
    def from_string(cls, level: str) -> 'LogLevel':
        """Convert string to LogLevel, defaulting to INFO for invalid values.
        
        Args:
            level: Log level string
            
        Returns:
            LogLevel enum value
        """
        try:
            return cls(level.lower())
        except ValueError:
            logger.warning(f"Invalid log level '{level}', defaulting to INFO")
            return cls.INFO

    def to_python_level(self) -> int:
        """Convert to Python logging level.
        
        Returns:
            Python logging module level constant
        """
        return getattr(logging, self.value.upper())

class ConfigDict(TypedDict, total=False):
    """Type definitions for configuration dictionary.
    
    All fields are optional to support partial updates.
    """
    name: str
    version: str
    description: str
    host: str
    port: int
    log_level: str
    log_file: Optional[str]
    plugin_dir: Optional[str]
    enabled_plugins: List[str]
    plugin_config: Dict[str, Any]
    allowed_origins: List[str]
    api_keys: Dict[str, str]
    resource_paths: List[str]
    max_resource_size: int
    dev_mode: bool
    reload: bool

ENV_MAPPINGS = {
    "MCP_NAME": "name",
    "MCP_VERSION": "version",
    "MCP_DESCRIPTION": "description",
    "MCP_HOST": "host",
    "MCP_SERVER_PORT": "port",
    "MCP_LOG_LEVEL": "log_level",
    "MCP_LOG_FILE": "log_file",
    "MCP_PLUGIN_DIR": "plugin_dir",
    "MCP_ENABLED_PLUGINS": "enabled_plugins",
    "MCP_ALLOWED_ORIGINS": "allowed_origins",
    "MCP_DEV_MODE": "dev_mode",
    "MCP_RELOAD": "reload",
}

@dataclass
class ServerConfig:
    """Server configuration settings."""
    
    # Core settings
    name: str
    version: str = "0.1.0"
    description: str = "MCP Server"
    
    # Network settings
    host: str = field(default_factory=lambda: os.getenv("MCP_HOST", "127.0.0.1"))
    port: int = field(
        default_factory=lambda: int(os.getenv("MCP_SERVER_PORT", "8000"))
    )
    
    # Logging settings
    log_level: LogLevel = field(
        default_factory=lambda: LogLevel.from_string(
            os.getenv("MCP_LOG_LEVEL", "info")
        )
    )
    log_file: Optional[str] = field(
        default_factory=lambda: os.getenv("MCP_LOG_FILE")
    )
    
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
    dev_mode: bool = field(
        default_factory=lambda: os.getenv("MCP_DEV_MODE", "").lower() == "true"
    )
    reload: bool = field(
        default_factory=lambda: os.getenv("MCP_RELOAD", "").lower() == "true"
    )

    @classmethod
    def from_env(cls, **kwargs) -> 'ServerConfig':
        """Create config from environment variables and kwargs.
        
        Environment variables take precedence over kwargs.
        
        Args:
            **kwargs: Default values for config
            
        Returns:
            ServerConfig instance
            
        Raises:
            ValidationError: If required fields are missing or invalid
        """
        config_dict = {k: v for k, v in kwargs.items() if v is not None}
        
        # Load from environment with type conversion
        env_updates: Dict[str, Any] = {}
        for env_var, config_key in ENV_MAPPINGS.items():
            if value := os.getenv(env_var):
                try:
                    if config_key in ("port", "max_resource_size"):
                        env_updates[config_key] = int(value)
                    elif config_key in ("enabled_plugins", "allowed_origins"):
                        env_updates[config_key] = value.split(",")
                    elif config_key in ("dev_mode", "reload"):
                        env_updates[config_key] = value.lower() == "true"
                    elif config_key == "plugin_dir":
                        env_updates[config_key] = Path(value)
                    elif config_key == "log_level":
                        env_updates[config_key] = LogLevel.from_string(value)
                    else:
                        env_updates[config_key] = value
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid value for {env_var}: {e}")

        # Environment overrides kwargs
        config_dict.update(env_updates)
        
        instance = cls(**config_dict)
        if errors := instance.validate():
            raise ValidationError("\n".join(errors))
            
        return instance

    @classmethod
    def from_file(cls, path: Path) -> 'ServerConfig':
        """Load configuration from a JSON file.
        
        Args:
            path: Path to config file
            
        Returns:
            ServerConfig instance
            
        Raises:
            ConfigError: If file cannot be read or parsed
            ValidationError: If config is invalid
        """
        try:
            config_dict = json.loads(path.read_text())
            
            # Convert path strings to Path objects
            if "plugin_dir" in config_dict:
                config_dict["plugin_dir"] = Path(config_dict["plugin_dir"])
            if "resource_paths" in config_dict:
                config_dict["resource_paths"] = [
                    Path(p) for p in config_dict["resource_paths"]
                ]
            if "log_level" in config_dict:
                config_dict["log_level"] = LogLevel.from_string(
                    config_dict["log_level"]
                )
                
            instance = cls(**config_dict)
            if errors := instance.validate():
                raise ValidationError("\n".join(errors))
                
            return instance
            
        except json.JSONDecodeError as e:
            raise ConfigError(f"Failed to parse config file: {e}")
        except Exception as e:
            raise ConfigError(f"Error loading config file: {e}")

    def to_file(self, path: Path) -> None:
        """Save configuration to a JSON file.
        
        Args:
            path: Path to save config
            
        Raises:
            ConfigError: If file cannot be written
        """
        try:
            # Convert to dict, handling Path objects
            config_dict = asdict(self)
            config_dict["resource_paths"] = [
                str(p) for p in self.resource_paths
            ]
            if self.plugin_dir:
                config_dict["plugin_dir"] = str(self.plugin_dir)
            config_dict["log_level"] = self.log_level.value
            
            atomic_write(path, json.dumps(config_dict, indent=2))
            
        except Exception as e:
            raise ConfigError(f"Failed to save config to {path}: {e}")

    def validate(self) -> List[str]:
        """Validate configuration settings.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Validate required fields
        if not self.name:
            errors.append("Server name is required")
        else:
            is_valid, error = check_package_name(self.name)
            if not is_valid:
                errors.append(f"Invalid server name: {error}")

        # Validate description
        if self.description:
            is_valid, error = validate_description(self.description)
            if not is_valid:
                errors.append(f"Invalid description: {error}")

        # Validate network settings
        if not 1 <= self.port <= 65535:
            errors.append(f"Port must be between 1 and 65535, got {self.port}")
            
        # Validate paths exist
        for path in self.resource_paths:
            if not path.exists():
                errors.append(f"Resource path does not exist: {path}")
                
        # Validate plugin configuration
        if self.plugin_dir:
            if not self.plugin_dir.exists():
                errors.append(f"Plugin directory does not exist: {self.plugin_dir}")
                
            # Check enabled plugins exist
            for plugin in self.enabled_plugins:
                plugin_file = self.plugin_dir / f"{plugin}.py"
                if not plugin_file.exists():
                    errors.append(f"Plugin file not found: {plugin_file}")
                    
        return errors

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
            log_file_path = Path(self.log_file)
            try:
                # Ensure log directory exists
                log_file_path.parent.mkdir(parents=True, exist_ok=True)
                
                log_config['handlers']['file'] = {
                    'class': 'logging.FileHandler',
                    'filename': self.log_file,
                    'formatter': 'default',
                    'level': self.log_level.to_python_level()
                }
                log_config['root']['handlers'].append('file')
            except OSError as e:
                logger.error(f"Failed to setup file logging: {e}")
            
        logging.config.dictConfig(log_config)

    def update(self, updates: ConfigDict) -> None:
        """Update config with new values.
        
        Args:
            updates: Dictionary of fields to update
            
        Raises:
            ValidationError: If updates would make config invalid
        """
        # Create temporary copy for validation
        updated = asdict(self)
        updated.update(updates)
        
        # Try to create new instance with updates
        temp_instance = self.__class__(**updated)
        if errors := temp_instance.validate():
            raise ValidationError("\n".join(errors))
            
        # Apply valid updates
        for key, value in updates.items():
            setattr(self, key, value)