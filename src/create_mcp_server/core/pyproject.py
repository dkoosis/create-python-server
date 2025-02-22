"""pyproject.toml file handling.

This module provides utilities for reading and modifying pyproject.toml files.
It handles:
- Loading and saving pyproject.toml
- Updating project metadata
- Managing dependencies and build settings
- Script entry points
"""

import toml
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import re

class PyProjectError(Exception):
    """Base exception for pyproject.toml operations."""
    pass

class InvalidProjectError(PyProjectError):
    """Raised when pyproject.toml is invalid."""
    pass

@dataclass
class ProjectMetadata:
    """Essential project metadata from pyproject.toml."""
    name: str
    version: str
    description: str
    requires_python: str
    dependencies: List[str]
    dev_dependencies: List[str]

class PyProject:
    """Handle pyproject.toml file operations."""
    
    def __init__(self, path: Path):
        """Initialize with path to pyproject.toml.
        
        Args:
            path: Path to pyproject.toml file
            
        Raises:
            PyProjectError: If file cannot be read or parsed
        """
        self.path = path
        try:
            self.data = toml.load(path) if path.exists() else {}
        except Exception as e:
            raise PyProjectError(f"Failed to load {path}: {e}")

    @property
    def metadata(self) -> ProjectMetadata:
        """Get project metadata.
        
        Returns:
            ProjectMetadata object containing core project info
            
        Raises:
            InvalidProjectError: If required metadata is missing
        """
        try:
            project = self.data.get("project", {})
            return ProjectMetadata(
                name=project["name"],
                version=project.get("version", "0.1.0"),
                description=project.get("description", ""),
                requires_python=project.get("requires-python", ">=3.8"),
                dependencies=project.get("dependencies", []),
                dev_dependencies=project.get("dev-dependencies", [])
            )
        except KeyError as e:
            raise InvalidProjectError(f"Missing required field in pyproject.toml: {e}")

    @property
    def scripts(self) -> Dict[str, str]:
        """Get project script entry points."""
        return self.data.get("project", {}).get("scripts", {})

    def update_metadata(
        self,
        version: Optional[str] = None,
        description: Optional[str] = None,
        requires_python: Optional[str] = None
    ) -> None:
        """Update project metadata.
        
        Args:
            version: New version string
            description: New project description
            requires_python: New Python version requirement
            
        The method only updates provided fields, leaving others unchanged.
        """
        if "project" not in self.data:
            self.data["project"] = {}
            
        if version is not None:
            self.data["project"]["version"] = version
        if description is not None:
            self.data["project"]["description"] = description
        if requires_python is not None:
            self.data["project"]["requires-python"] = requires_python

    def add_dependency(
        self,
        package: str,
        version: Optional[str] = None,
        dev: bool = False
    ) -> None:
        """Add a package dependency.
        
        Args:
            package: Package name
            version: Optional version specifier
            dev: Whether this is a development dependency
        """
        if "project" not in self.data:
            self.data["project"] = {}
            
        dep_type = "dev-dependencies" if dev else "dependencies"
        if dep_type not in self.data["project"]:
            self.data["project"][dep_type] = []
            
        # Format dependency string
        dep_str = package
        if version:
            dep_str += f">={version}"
            
        if dep_str not in self.data["project"][dep_type]:
            self.data["project"][dep_type].append(dep_str)

    def add_script(self, name: str, cmd: str) -> None:
        """Add a script entry point.
        
        Args:
            name: Script name
            cmd: Command to run
        """
        if "project" not in self.data:
            self.data["project"] = {}
        if "scripts" not in self.data["project"]:
            self.data["project"]["scripts"] = {}
            
        self.data["project"]["scripts"][name] = cmd

    def set_build_system(
        self,
        requires: Optional[List[str]] = None,
        build_backend: Optional[str] = None
    ) -> None:
        """Set build system configuration.
        
        Args:
            requires: List of build dependencies
            build_backend: Build backend to use
        """
        if "build-system" not in self.data:
            self.data["build-system"] = {}
            
        if requires is not None:
            self.data["build-system"]["requires"] = requires
        if build_backend is not None:
            self.data["build-system"]["build-backend"] = build_backend

    def save(self) -> None:
        """Save changes back to pyproject.toml.
        
        Raises:
            PyProjectError: If file cannot be written
        """
        try:
            # Format with consistent indentation
            toml_str = toml.dumps(self.data)
            
            # Ensure parent directory exists
            self.path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write atomically by using a temporary file
            temp_path = self.path.with_suffix('.tmp')
            temp_path.write_text(toml_str)
            temp_path.replace(self.path)
            
        except Exception as e:
            raise PyProjectError(f"Failed to save {self.path}: {e}")

    @staticmethod
    def create_default(
        path: Path,
        name: str,
        version: str = "0.1.0",
        description: str = "",
        python_version: str = ">=3.8"
    ) -> "PyProject":
        """Create a new pyproject.toml with default settings.
        
        Args:
            path: Where to create the file
            name: Project name
            version: Project version
            description: Project description
            python_version: Required Python version
            
        Returns:
            New PyProject instance
        """
        project = PyProject(path)
        project.data = {
            "project": {
                "name": name,
                "version": version,
                "description": description,
                "requires-python": python_version,
                "dependencies": [],
                "dev-dependencies": [],
                "scripts": {},
                "authors": [],
                "license": {"text": "MIT"},
                "classifiers": [
                    "Development Status :: 3 - Alpha",
                    "Intended Audience :: Developers",
                    "License :: OSI Approved :: MIT License",
                    "Programming Language :: Python :: 3",
                ]
            },
            "build-system": {
                "requires": ["hatchling"],
                "build-backend": "hatchling.build"
            }
        }
        project.save()
        return project

def update_pyproject_settings(
    project_path: Path,
    version: Optional[str] = None,
    description: Optional[str] = None
) -> None:
    """Update version and description in pyproject.toml.
    
    Args:
        project_path: Directory containing pyproject.toml
        version: New version string
        description: New project description
        
    Raises:
        PyProjectError: If update fails
    """
    try:
        pyproject_path = project_path / "pyproject.toml"
        project = PyProject(pyproject_path)
        project.update_metadata(version=version, description=description)
        project.save()
        
    except PyProjectError:
        raise
    except Exception as e:
        raise PyProjectError(f"Failed to update project settings: {e}")
