"""Claude.app integration utilities.

This module handles integration with Claude.app, specifically for
registering MCP servers with Claude Desktop. It provides:

- Configuration file handling
- Server registration
- Platform-specific path resolution
- Atomic file operations
- Validation

File: create_mcp_server/utils/claude.py
"""

import json
import logging
import os
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .files import atomic_write, atomic_replace, FileError
from .validation import (
    ValidationResult,
    check_package_name,
    validate_url
)

logger = logging.getLogger(__name__)

class ClaudeError(Exception):
    """Base exception for Claude.app operations."""
    pass

class ConfigError(ClaudeError):
    """Raised when there are issues with the Claude config file."""
    pass

class ValidationError(ClaudeError):
    """Raised when validation fails."""
    pass

@dataclass
class ServerRegistration:
    """MCP server registration details."""
    name: str
    command: str
    args: List[str]
    env: Dict[str, str]
    working_dir: Path
    enabled: bool = True
    health_check_url: Optional[str] = None
    description: Optional[str] = None

    def validate(self) -> List[str]:
        """Validate registration details.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Validate name
        name_result = check_package_name(self.name)
        if not name_result.is_valid:
            errors.append(f"Invalid server name: {name_result.message}")
            
        # Validate working directory
        if not self.working_dir.exists():
            errors.append(f"Working directory does not exist: {self.working_dir}")
            
        # Validate health check URL if provided
        if self.health_check_url:
            url_result = validate_url(self.health_check_url)
            if not url_result.is_valid:
                errors.append(f"Invalid health check URL: {url_result.message}")
                
        return errors

    def to_dict(self) -> Dict[str, Any]:
        """Convert registration to dictionary format.
        
        Returns:
            Dictionary representation for JSON serialization
        """
        data = asdict(self)
        data['working_dir'] = str(self.working_dir)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServerRegistration':
        """Create registration from dictionary.
        
        Args:
            data: Dictionary data
            
        Returns:
            ServerRegistration instance
            
        Raises:
            ValidationError: If data is invalid
        """
        try:
            # Convert working_dir back to Path
            if 'working_dir' in data:
                data['working_dir'] = Path(data['working_dir'])
                
            return cls(**data)
        except Exception as e:
            raise ValidationError(f"Invalid registration data: {e}")

def get_claude_config_path() -> Optional[Path]:
    """Get the platform-specific Claude config directory path.
    
    Returns:
        Path to config directory if Claude is installed, None otherwise
        
    The config directory locations are:
    - Windows: %APPDATA%/Claude
    - macOS: ~/Library/Application Support/Claude
    - Linux: ~/.config/claude
    """
    system = platform.system().lower()
    
    if system == "windows":
        base = os.environ.get("APPDATA")
        if not base:
            return None
        path = Path(base) / "Claude"
    elif system == "darwin":
        path = Path.home() / "Library" / "Application Support" / "Claude"
    elif system == "linux":
        path = Path.home() / ".config" / "claude"
    else:
        logger.debug(f"Claude Desktop is not supported on {system}")
        return None

    if path.exists():
        return path
    
    logger.debug(f"Claude config directory not found at {path}")
    return None

def has_claude_app() -> bool:
    """Check if Claude Desktop app is installed.
    
    Returns:
        True if Claude Desktop is installed and config directory exists
    """
    return get_claude_config_path() is not None

def load_claude_config(config_path: Path) -> Dict[str, Any]:
    """Load and parse the Claude config file.
    
    Args:
        config_path: Path to the config file
        
    Returns:
        Parsed config data
        
    Raises:
        ConfigError: If config file cannot be read or parsed
    """
    try:
        if not config_path.exists():
            return {"mcpServers": {}}
            
        with config_path.open('r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Ensure mcpServers section exists
        if "mcpServers" not in config_data:
            config_data["mcpServers"] = {}
            
        # Validate server registrations
        for name, data in config_data["mcpServers"].items():
            try:
                registration = ServerRegistration.from_dict(data)
                if errors := registration.validate():
                    logger.warning(
                        f"Invalid server registration '{name}': {errors}"
                    )
            except ValidationError as e:
                logger.warning(f"Invalid server data for '{name}': {e}")
            
        return config_data
        
    except json.JSONDecodeError as e:
        raise ConfigError(f"Failed to parse Claude config: {e}")
    except Exception as e:
        raise ConfigError(f"Error reading Claude config: {e}")

def save_claude_config(config_path: Path, config_data: Dict[str, Any]) -> None:
    """Save config data back to the Claude config file.
    
    Args:
        config_path: Path to the config file
        config_data: Configuration data to save
        
    Raises:
        ConfigError: If config cannot be saved
    """
    try:
        # Convert any Path objects to strings
        if "mcpServers" in config_data:
            for server in config_data["mcpServers"].values():
                if isinstance(server.get("working_dir"), Path):
                    server["working_dir"] = str(server["working_dir"])
        
        # Write atomically
        with atomic_replace(config_path) as temp_path:
            with temp_path.open('w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
                
    except (FileError, OSError) as e:
        raise ConfigError(f"Failed to save Claude config: {e}")

def get_server_config(
    config_data: Dict[str, Any],
    server_name: str
) -> Optional[ServerRegistration]:
    """Get configuration for a specific MCP server.
    
    Args:
        config_data: Claude config data
        server_name: Name of the server to look up
        
    Returns:
        ServerRegistration if found and valid, None otherwise
    """
    try:
        if server_data := config_data.get("mcpServers", {}).get(server_name):
            return ServerRegistration.from_dict(server_data)
    except ValidationError as e:
        logger.warning(f"Invalid server data for '{server_name}': {e}")
    return None

def update_claude_config(name: str, path: Path) -> bool:
    """Register an MCP server with Claude Desktop.
    
    Args:
        name: Name of the MCP server
        path: Path to the server installation
        
    Returns:
        True if registration successful, False otherwise
        
    This function:
    1. Locates the Claude config directory
    2. Loads existing config
    3. Adds/updates server registration
    4. Saves updated config
    
    The server will be registered to run with UV in its own environment.
    """
    try:
        # Validate inputs
        name_result = check_package_name(name)
        if not name_result.is_valid:
            logger.error(f"Invalid server name: {name_result.message}")
            return False
            
        if not path.exists():
            logger.error(f"Server path does not exist: {path}")
            return False
            
        config_dir = get_claude_config_path()
        if not config_dir:
            logger.warning("Claude Desktop not found, skipping registration")
            return False
            
        config_file = config_dir / "claude_desktop_config.json"
        
        # Load existing config
        config_data = load_claude_config(config_file)
        
        # Check if server already registered
        if name in config_data["mcpServers"]:
            logger.warning(f"Server '{name}' already registered with Claude")
            return False
        
        # Create registration
        registration = ServerRegistration(
            name=name,
            command="uv",
            args=["--directory", str(path), "run", name],
            env={},
            working_dir=path,
            health_check_url=f"http://localhost:8000/health",
            description=f"MCP server '{name}'"
        )
        
        # Validate registration
        if errors := registration.validate():
            logger.error(
                f"Invalid server registration: {'; '.join(errors)}"
            )
            return False
        
        # Add registration
        config_data["mcpServers"][name] = registration.to_dict()
        
        # Save updated config
        save_claude_config(config_file, config_data)
        logger.info(f"Successfully registered server '{name}' with Claude")
        
        return True
        
    except ConfigError as e:
        logger.error(f"Failed to register server with Claude: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error registering server: {e}")
        return False

def remove_server_registration(name: str) -> bool:
    """Remove an MCP server registration from Claude Desktop.
    
    Args:
        name: Name of the server to remove
        
    Returns:
        True if removal successful, False otherwise
    """
    try:
        config_dir = get_claude_config_path()
        if not config_dir:
            logger.warning("Claude Desktop not found")
            return False
            
        config_file = config_dir / "claude_desktop_config.json"
        
        # Load existing config
        config_data = load_claude_config(config_file)
        
        # Remove server if registered
        if name in config_data["mcpServers"]:
            del config_data["mcpServers"][name]
            save_claude_config(config_file, config_data)
            logger.info(f"Removed server '{name}' registration from Claude")
            return True
            
        logger.warning(f"Server '{name}' not found in Claude configuration")
        return False
        
    except Exception as e:
        logger.error(f"Failed to remove server registration: {e}")
        return False