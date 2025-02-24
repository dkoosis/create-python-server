"""Project creation and initialization.

This module handles the core project creation logic including:
- Directory structure creation
- Virtual environment setup
- Dependency management
- Project file generation

File: create_mcp_server/core/project.py
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set

from create_mcp_server.core.pyproject import PyProject, PyProjectError
from create_mcp_server.core.template import ServerTemplate, TemplateError
from create_mcp_server.server.config import ServerConfig, ValidationError
from create_mcp_server.utils.files import atomic_write, safe_rmtree
from create_mcp_server.utils.process import (
    ensure_uv_installed, 
    run_uv_command, 
    ProcessError,
    PROCESS_TIMEOUT
)
from create_mcp_server.utils.validation import check_package_name

logger = logging.getLogger(__name__)

class ProjectError(Exception):
    """Base exception for project creation errors."""
    pass

class ProjectCreator:
    """Handles MCP server project creation and setup."""
    
    # Default project structure
    DIRS = [
        "src",
        "tests",
        "docs",
        "scripts",
    ]
    
    # Default dependencies
    DEFAULT_DEPENDENCIES = [
        "fastapi>=0.68.0",
        "uvicorn>=0.15.0",
        "jinja2>=3.0.0",
        "toml>=0.10.2",
        "python-dotenv>=0.19.0",
    ]
    
    # Development dependencies
    DEV_DEPENDENCIES = [
        "pytest>=7.0.0",
        "black>=22.0.0",
        "ruff>=0.1.0",
        "mypy>=1.0.0",
    ]
    
    def __init__(
        self,
        path: Path,
        name: str,
        version: str = "0.1.0",
        description: Optional[str] = None,
        python_version: str = ">=3.10"
    ):
        """Initialize project creator.
        
        Args:
            path: Project parent directory
            name: Project name
            version: Project version
            description: Optional project description
            python_version: Required Python version
            
        Raises:
            ProjectError: If project name is invalid
        """
        # Validate project name immediately
        is_valid, error = check_package_name(name)
        if not is_valid:
            raise ProjectError(f"Invalid project name: {error}")
            
        self.path = path
        self.name = name
        self.version = version
        self.description = description or f"MCP server '{name}'"
        self.python_version = python_version
        self.project_dir = path / name
        
        # Track created resources for cleanup
        self._created_paths: Set[Path] = set()
        self._created_venv = False

    def create(self) -> None:
        """Create and initialize the project.
        
        Creates directory structure, virtual environment, and base files.
        
        Raises:
            ProjectError: If project creation fails
            PyProjectError: If pyproject.toml creation fails
        """
        try:
            # Ensure UV is installed
            ensure_uv_installed()
            
            # Create project directory structure
            self._create_directories()
            
            # Create virtual environment
            self._create_venv()
            
            # Create pyproject.toml
            self._create_pyproject()
            
            # Generate server config
            self._create_server_config()
            
            # Install dependencies
            if self._should_install_deps():
                self.install_dependencies()
                
            logger.info(f"Successfully created project in {self.project_dir}")
            
        except Exception as e:
            self._cleanup()
            raise ProjectError(f"Project creation failed: {e}")

    def _create_directories(self) -> None:
        """Create project directory structure.
        
        Raises:
            ProjectError: If directory creation fails
        """
        try:
            # Create main project directory
            self.project_dir.mkdir(parents=True, exist_ok=True)
            self._created_paths.add(self.project_dir)
            
            # Create standard directories
            for dirname in self.DIRS:
                dir_path = self.project_dir / dirname
                dir_path.mkdir(parents=True, exist_ok=True)
                self._created_paths.add(dir_path)
                
            # Create package directory
            pkg_dir = self.project_dir / "src" / self.name
            pkg_dir.mkdir(parents=True, exist_ok=True)
            self._created_paths.add(pkg_dir)
            
            # Create __init__.py files
            for parent in [pkg_dir, pkg_dir / "tests"]:
                init_file = parent / "__init__.py"
                atomic_write(init_file, "")
                self._created_paths.add(init_file)
                
        except OSError as e:
            raise ProjectError(f"Failed to create directory structure: {e}")

    def _create_venv(self) -> None:
        """Create virtual environment using UV.
        
        Raises:
            ProjectError: If venv creation fails
        """
        try:
            run_uv_command(
                ["venv"],
                cwd=self.project_dir,
                timeout=PROCESS_TIMEOUT,
                check=True
            )
            self._created_venv = True
            
        except ProcessError as e:
            raise ProjectError(f"Failed to create virtual environment: {e}")

    def _create_pyproject(self) -> None:
        """Create pyproject.toml with project metadata.
        
        Raises:
            PyProjectError: If file creation fails
        """
        pyproject = PyProject.create_default(
            self.project_dir / "pyproject.toml",
            name=self.name,
            version=self.version,
            description=self.description,
            python_version=self.python_version
        )
        
        # Add standard dependencies
        for dep in self.DEFAULT_DEPENDENCIES:
            pyproject.add_dependency(dep)
            
        # Add development dependencies
        for dep in self.DEV_DEPENDENCIES:
            pyproject.add_dependency(dep, dev=True)
            
        pyproject.save()
        self._created_paths.add(pyproject.path)

    def _create_server_config(self) -> None:
        """Create server configuration.
        
        Raises:
            ValidationError: If config is invalid
            ConfigError: If config cannot be saved
        """
        config = ServerConfig(
            name=self.name,
            version=self.version,
            description=self.description
        )
        
        # Validate config
        if errors := config.validate():
            raise ValidationError("\n".join(errors))
            
        # Save config
        config_path = self.project_dir / "server_config.json"
        config.to_file(config_path)
        self._created_paths.add(config_path)

    def install_dependencies(
        self, 
        dependencies: Optional[List[str]] = None,
        dev: bool = False
    ) -> None:
        """Install project dependencies.
        
        Args:
            dependencies: List of packages to install. If None, installs defaults.
            dev: Whether to install development dependencies
            
        Raises:
            ProjectError: If dependency installation fails
        """
        if dependencies is None:
            dependencies = self.DEFAULT_DEPENDENCIES
            if dev:
                dependencies.extend(self.DEV_DEPENDENCIES)
            
        try:
            run_uv_command(
                ["pip", "install", *dependencies],
                cwd=self.project_dir,
                timeout=PROCESS_TIMEOUT,
                check=True
            )
            logger.info(f"Installed {len(dependencies)} packages")
            
        except ProcessError as e:
            raise ProjectError(f"Failed to install dependencies: {e}")

    def _should_install_deps(self) -> bool:
        """Check if dependencies should be installed.
        
        Returns:
            True if deps should be installed, False otherwise
        """
        return (
            self._created_venv and 
            (self.project_dir / ".venv").exists()
        )

    def _cleanup(self) -> None:
        """Clean up created resources on failure."""
        logger.info("Cleaning up created resources")
        
        # Remove created paths in reverse order
        for path in sorted(self._created_paths, reverse=True):
            try:
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    safe_rmtree(path)
            except OSError as e:
                logger.warning(f"Failed to clean up {path}: {e}")
                
        # Clean up virtual environment
        if self._created_venv:
            venv_path = self.project_dir / ".venv"
            try:
                safe_rmtree(venv_path)
            except OSError as e:
                logger.warning(f"Failed to clean up venv: {e}")

def create_project(
    path: Path,
    name: str,
    version: str = "0.1.0",
    description: Optional[str] = None,
    python_version: str = ">=3.10",
    install_deps: bool = True
) -> None:
    """Create a new MCP server project.
    
    This is the main entry point for project creation.
    
    Args:
        path: Parent directory for project
        name: Project name
        version: Project version
        description: Optional project description
        python_version: Required Python version
        install_deps: Whether to install default dependencies
        
    Raises:
        ProjectError: If project creation fails
        PyProjectError: If pyproject.toml creation fails
        ValidationError: If config validation fails
    """
    creator = ProjectCreator(
        path, 
        name, 
        version, 
        description,
        python_version
    )
    
    creator.create()
    
    if install_deps:
        creator.install_dependencies()