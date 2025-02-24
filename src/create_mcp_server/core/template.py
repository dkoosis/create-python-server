"""Template generation for MCP servers.

This module manages MCP server template rendering and validation.
Templates are organized in a structured hierarchy with predefined
naming conventions and output locations.

File: create-mcp-server/core/template.py
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from jinja2 import (
    Environment,
    FileSystemLoader,
    TemplateError as Jinja2Error,
    TemplateNotFound,
    select_autoescape
)

from ..server.config import ServerConfig
from ..utils.files import (
    atomic_write,
    ensure_directory,
    safe_rmtree,
    atomic_replace
)
from ..utils.validation import validate_description

logger = logging.getLogger(__name__)

class TemplateError(Exception):
    """Base exception for template-related errors."""
    pass

class ValidationError(TemplateError):
    """Raised when template validation fails."""
    pass

class RenderError(TemplateError):
    """Raised when template rendering fails."""
    pass

class ServerTemplate:
    """Handles MCP server template generation."""
    
    # Template file mapping: (template_name, output_path)
    TEMPLATE_FILES = {
        # Server core
        "server/main.py.jinja2": "server.py",
        "server/__init__.py.jinja2": "__init__.py",
        "server/config.py.jinja2": "config.py",
        "server/core.py.jinja2": "core.py",
        
        # Plugins
        "plugins/__init__.py.jinja2": "plugins/__init__.py",
        "plugins/example.py.jinja2": "plugins/example.py",
        
        # Tests
        "tests/__init__.py.jinja2": "tests/__init__.py",
        "tests/test_server.py.jinja2": "tests/test_server.py",
        
        # Documentation
        "README.md.jinja2": "../README.md",  # Relative to package dir
        "docs/api.md.jinja2": "../docs/api.md",
        "docs/usage.md.jinja2": "../docs/usage.md",
    }
    
    # Required files that must exist after generation
    REQUIRED_FILES = [
        "server.py",
        "__init__.py",
        "config.py",
        "README.md"
    ]
    
    def __init__(self, template_dir: Optional[Path] = None):
        """Initialize template engine.
        
        Args:
            template_dir: Custom template directory. If None, uses default.
            
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
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )
        
        # Track generated files for cleanup
        self._generated_files: Set[Path] = set()
        
        # Validate templates on initialization
        self._validate_templates()

    def create_server(
        self,
        project_dir: Path,
        config: ServerConfig,
        package_dir: Path
    ) -> None:
        """Create a new MCP server from templates.
        
        Args:
            project_dir: Project root directory
            config: Server configuration
            package_dir: Python package directory
            
        Raises:
            TemplateError: If server creation fails
            ValidationError: If validation fails
        """
        try:
            # Clear generated files tracking
            self._generated_files.clear()
            
            # Create directories
            self._create_directories(package_dir)
            
            # Validate configuration
            self._validate_config(config)
            
            # Prepare template context
            context = self._create_context(config, package_dir)
            
            # Render all templates
            for template_name, rel_output_path in self.TEMPLATE_FILES.items():
                output_path = self._get_output_path(
                    package_dir,
                    rel_output_path
                )
                self._render_template(template_name, output_path, context)
                
            # Validate output
            self._validate_output(package_dir)
            
            logger.info(f"Created MCP server in {project_dir}")
            
        except Exception as e:
            self._cleanup()
            if isinstance(e, (ValidationError, RenderError)):
                raise
            raise TemplateError(f"Failed to create server: {e}")

    def _validate_templates(self) -> None:
        """Validate all template files exist and are readable.
        
        Raises:
            ValidationError: If template validation fails
        """
        errors = []
        for template_name in self.TEMPLATE_FILES:
            try:
                self.env.get_template(template_name)
            except TemplateNotFound:
                errors.append(f"Template not found: {template_name}")
            except Exception as e:
                errors.append(f"Invalid template {template_name}: {e}")
                
        if errors:
            raise ValidationError(
                "Template validation failed:\n" + "\n".join(errors)
            )

    def _validate_config(self, config: ServerConfig) -> None:
        """Validate server configuration.
        
        Args:
            config: Server configuration to validate
            
        Raises:
            ValidationError: If configuration is invalid
        """
        if errors := config.validate():
            raise ValidationError(
                "Invalid server configuration:\n" + "\n".join(errors)
            )
            
        # Additional template-specific validation
        if config.description:
            is_valid, error = validate_description(config.description)
            if not is_valid:
                raise ValidationError(f"Invalid description: {error}")

    def _create_directories(self, package_dir: Path) -> None:
        """Create required directories.
        
        Args:
            package_dir: Base package directory
            
        Raises:
            TemplateError: If directory creation fails
        """
        try:
            # Create package directory structure
            directories = [
                package_dir,
                package_dir / "tests",
                package_dir / "plugins",
                package_dir.parent / "docs",
            ]
            
            for directory in directories:
                ensure_directory(directory)
                
        except Exception as e:
            raise TemplateError(f"Failed to create directories: {e}")

    def _create_context(
        self,
        config: ServerConfig,
        package_dir: Path
    ) -> Dict[str, Any]:
        """Create template rendering context.
        
        Args:
            config: Server configuration
            package_dir: Package directory
            
        Returns:
            Template context dictionary
        """
        return {
            "project_name": config.name,
            "package_name": package_dir.name,
            "version": config.version,
            "description": config.description,
            "host": config.host,
            "port": config.port,
            "log_level": config.log_level.value,
        }

    def _get_output_path(self, package_dir: Path, rel_path: str) -> Path:
        """Get absolute output path for a template file.
        
        Args:
            package_dir: Package directory
            rel_path: Relative output path
            
        Returns:
            Absolute Path for output file
        """
        if rel_path.startswith("../"):
            # Handle paths relative to project root
            return package_dir.parent / rel_path[3:]
        return package_dir / rel_path

    def _render_template(
        self,
        template_name: str,
        output_path: Path,
        context: Dict[str, Any]
    ) -> None:
        """Render a single template.
        
        Args:
            template_name: Template file name
            output_path: Output file path
            context: Template rendering context
            
        Raises:
            RenderError: If rendering fails
        """
        try:
            template = self.env.get_template(template_name)
            content = template.render(**context)
            
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write atomically
            atomic_write(output_path, content)
            self._generated_files.add(output_path)
            logger.debug(f"Created {output_path}")
            
        except Jinja2Error as e:
            raise RenderError(f"Template render error in {template_name}: {e}")
        except Exception as e:
            raise RenderError(f"Failed to render {template_name}: {e}")

    def _validate_output(self, package_dir: Path) -> None:
        """Validate generated server files.
        
        Args:
            package_dir: Package directory to validate
            
        Raises:
            ValidationError: If validation fails
        """
        errors = []
        
        # Check required files exist
        for filename in self.REQUIRED_FILES:
            file_path = package_dir / filename
            if not file_path.exists():
                errors.append(f"Missing required file: {filename}")
                continue
                
            # Basic content validation
            try:
                content = file_path.read_text()
                if filename == "server.py" and "class MCPServer" not in content:
                    errors.append(
                        "server.py is missing required MCPServer class"
                    )
            except Exception as e:
                errors.append(f"Failed to validate {filename}: {e}")
                    
        if errors:
            raise ValidationError(
                "Template validation failed:\n" + "\n".join(errors)
            )

    def _cleanup(self) -> None:
        """Clean up generated files on failure."""
        logger.info("Cleaning up generated files")
        
        for path in sorted(self._generated_files, reverse=True):
            try:
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    safe_rmtree(path)
            except OSError as e:
                logger.warning(f"Failed to clean up {path}: {e}")
                
        self._generated_files.clear()