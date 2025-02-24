"""Template generation for MCP servers.

This module handles the creation and rendering of MCP server templates.
It provides a clean separation between template logic and other
concerns like configuration and CLI interaction.

Key responsibilities:
- Managing template files and structure
- Rendering templates with provided context
- Validating template output

File: create-mcp-server/core/template.py
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader
from ..server.config import ServerConfig
from ..utils.files import atomic_write, safe_rmtree
from ..utils.validation import check_project_path


logger = logging.getLogger(__name__)

class TemplateError(Exception):
    """Base exception for template-related errors."""
    pass

class RenderError(TemplateError):
    """Raised when template rendering fails."""
    pass

class ServerTemplate:
    """Handles MCP server template generation.
    
    This class manages the creation of new MCP servers from templates,
    handling both the file structure and content generation.
    """
    
    # Define standard template files and their destinations
    TEMPLATE_FILES = {
        "server.py.jinja2": "server.py",
        "__init__.py.jinja2": "__init__.py",
        "README.md.jinja2": "README.md",
        "config.py.jinja2": "config.py",
        "core.py.jinja2": "core.py"
    }
    
    def __init__(self, template_dir: Optional[Path] = None):
        """Initialize template engine.
        
        Args:
            template_dir: Custom template directory path. If None, uses default.
            
        Raises:
            TemplateError: If template directory is invalid
        """
        if template_dir is None:
            template_dir = Path(__file__).parent.parent / "templates"
            
        if not template_dir.exists():
            raise TemplateError(f"Template directory not found: {template_dir}")
            
        self.template_dir = template_dir
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )
        
    def create_server(
        self,
        target_dir: Path,
        config: ServerConfig,
        package_dir: Path
    ) -> None:
        """Create a new MCP server from templates.
        
        Args:
            target_dir: Directory to create server in
            config: Server configuration
            package_dir: Python package directory for server code
            
        Raises:
            TemplateError: If server creation fails
        """
        # Validate paths
        is_valid, error = check_project_path(target_dir)
        if not is_valid:
            raise TemplateError(f"Invalid target directory: {error}")
        
        try:
            # Create necessary directories
            package_dir.mkdir(parents=True, exist_ok=True)
            (package_dir / "tests").mkdir(parents=True, exist_ok=True)
            (package_dir / "plugins").mkdir(parents=True, exist_ok=True)
            
            # Prepare template context
            context = {
                "server_name": config.name,
                "server_version": config.version,
                "server_description": config.description,
                "server_host": config.host,
                "server_port": config.port,
                "log_level": config.log_level.value,
            }
            
            # Render and write templates
            for template_file, output_name in self.TEMPLATE_FILES.items():
                try:
                    template = self.env.get_template(template_file)
                    
                    # Determine output path
                    if output_name == "README.md":
                        output_path = target_dir / output_name
                    else:
                        output_path = package_dir / output_name
                        
                    # Ensure parent directory exists
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Render and write atomically
                    content = template.render(**context)
                    atomic_write(output_path, content)
                    
                    logger.debug(f"Created {output_path}")
                    
                except Exception as e:
                    logger.error(f"Failed to render {template_file}: {e}")
                    raise TemplateError(f"Failed to render {template_file}: {e}")
                    
        except Exception as e:
            # Clean up on failure
            logger.error(f"Failed to create server: {e}")
            safe_rmtree(target_dir)
            raise TemplateError(f"Failed to create server: {e}")
        
        logger.info(f"Created MCP server in {target_dir}")
        
        # Run validation
        errors = self.validate_output(target_dir)
        if errors:
            error_list = "\n  - ".join(errors)
            logger.warning(f"Template validation issues:\n  - {error_list}")

    def _build_context(self, config: ServerConfig) -> Dict:
        """Build template rendering context.
        
        Args:
            config: Server configuration
            
        Returns:
            Dict of template variables
        """
        return {
            "server_name": config.name,
            "server_version": config.version,
            "server_description": config.description,
            "server_host": config.host,
            "server_port": config.port,
            "log_level": config.log_level.value,
        }
        
    def _render_templates(
        self,
        context: Dict,
        package_dir: Path,
        target_dir: Path
    ) -> None:
        """Render and write all template files.
        
        Args:
            context: Template rendering context
            package_dir: Package directory for Python files
            target_dir: Target project directory
            
        Raises:
            TemplateError: If rendering fails
        """
        for template_file, output_name in self.TEMPLATE_FILES.items():
            try:
                template = self.env.get_template(template_file)
                
                # Determine output path based on file type
                if output_name == "README.md":
                    output_path = target_dir / output_name
                else:
                    output_path = package_dir / output_name
                    
                # Render and write
                content = template.render(**context)
                output_path.write_text(content)
                
            except Exception as e:
                raise RenderError(f"Failed to render {template_file}: {e}")
                
    def validate_output(self, target_dir: Path) -> List[str]:
        """Validate generated server files.
        
        Args:
            target_dir: Directory containing generated server
            
        Returns:
            List of validation error messages, empty if valid
        """
        errors = []
        
        # Check required files exist
        required_files = [
            target_dir / "README.md",
            target_dir / "pyproject.toml"
        ]
        
        for file in required_files:
            if not file.exists():
                errors.append(f"Missing required file: {file.name}")
                
        # Basic content validation
        try:
            main_py = target_dir / "server.py"
            if main_py.exists():
                content = main_py.read_text()
                if "class MCPServer" not in content:
                    errors.append("server.py missing MCPServer class")
        except Exception as e:
            errors.append(f"Failed to validate server.py: {e}")
            
        return errors