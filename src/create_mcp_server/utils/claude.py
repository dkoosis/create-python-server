"""Claude.app integration utilities.

This module handles integration with Claude.app, specifically for registering
MCP servers with Claude Desktop. It provides:
- Configuration file handling
- Server registration
- Platform-specific path resolution
"""

import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class ClaudeError(Exception):
    """Base exception for Claude.app operations."""
    pass

class ConfigError(ClaudeError):
    """Raised when there are issues with the Claude config file."""
    pass

def get_claude_config_path() -> Optional[Path]:
    """Get the platform-specific Claude config directory path.
    
    Returns:
        Path to config directory if Claude is installed, None otherwise
        
    The config directory locations are:
    - Windows: %APPDATA%/Claude
    - macOS: ~/Library/Application Support/Claude
    - Linux: Not currently supported
    """
    if sys.platform == "win32":
        path = Path(Path.home(), "AppData", "Roaming", "Claude")
    elif sys.platform == "darwin":
        path = Path(Path.home(), "Library", "Application Support", "Claude")
    else:
        logger.debug("Claude Desktop is not supported on this platform")
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
            
        config_data = json.loads(config_path.read_text())
        
        # Ensure mcpServers section exists
        if "mcpServers" not in config_data:
            config_data["mcpServers"] = {}
            
        return config_data
        
    except json.JSONDecodeError as e:
        raise ConfigError(f"Failed to parse Claude config: {e}")
    except Exception as e:
        raise ConfigError(f"Error reading Claude config: {e}")

def save_claude_config(config_path: Path, config_data: Dict[str, Any]) -> None:
    """Save config data back to the Claude config file.
    
    Args:
        config_path: Path to the config file
        config_data: Config data to save
        
    Raises:
        ConfigError: If config cannot be saved
    """
    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write atomically using a temporary file
        temp_path = config_path.with_suffix('.tmp')
        temp_path.write_text(json.dumps(config_data, indent=2))
        temp_path.replace(config_path)
        
    except Exception as e:
        raise ConfigError(f"Failed to save Claude config: {e}")

def get_server_config(
    config_data: Dict[str, Any],
    server_name: str
) -> Optional[Dict[str, Any]]:
    """Get configuration for a specific MCP server.
    
    Args:
        config_data: Claude config data
        server_name: Name of the server to look up
        
    Returns:
        Server config if found, None otherwise
    """
    return config_data.get("mcpServers", {}).get(server_name)

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
        
        # Add server configuration
        config_data["mcpServers"][name] = {
            "command": "uv",
            "args": ["--directory", str(path), "run", name],
            "env": {}  # Can be extended with custom environment variables
        }
        
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