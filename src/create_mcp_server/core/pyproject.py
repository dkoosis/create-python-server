"""pyproject.toml file handling.

This module provides utilities for reading and modifying pyproject.toml
files. It handles:

- Loading and saving pyproject.toml
- Project metadata management
- Dependency management
- Build settings
- Script entry points
- Atomic file operations

File: create_mcp_server/core/pyproject.py
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import toml
from packaging.specifiers import SpecifierSet
from packaging.version import Version, parse

from ..utils.files import atomic_write, FileError
from ..utils.validation import (
    ValidationResult,
    check_package_name,
    check_version,
    validate_description
)

logger = logging.getLogger(__name__)

class PyProjectError(Exception):
    """Base exception for pyproject.toml operations."""
    pass

class InvalidProjectError(PyProjectError):
    """Raised when pyproject.toml is invalid."""
    pass

class DependencyError(PyProjectError):
    """Raised when dependency operations fail."""
    pass

@dataclass
class Dependency:
    """Package dependency information."""
    name: str
    version_spec: Optional[str] = None
    extras: Set[str] = field(default_factory=set)
    optional: bool = False
    
    def __str__(self) -> str:
        """Convert to dependency string format."""
        parts = [self.name]
        if self.version_spec:
            parts.append(self.version_spec)
        if self.extras:
            parts.append(f"[{','.join(sorted(self.extras))}]")
        return ''.join(parts)
    
    @classmethod
    def from_string(cls, dep_string: str) -> 'Dependency':
        """Parse dependency from string.
        
        Args:
            dep_string: Dependency specification string
            
        Returns:
            Dependency instance
            
        Raises:
            DependencyError: If string cannot be parsed
        """
        try:
            # Extract extras
            extras_match = re.match(r'([^[]+)(?:\[(.*)\])?', dep_string)
            if not extras_match:
                raise ValueError(f"Invalid dependency format: {dep_string}")
                
            name_ver, extras_str = extras_match.groups()
            extras = {e.strip() for e in extras_str.split(',')} if extras_str else set()
            
            # Extract version
            parts = name_ver.split('>=')
            name = parts[0].strip()
            version_spec = f">={parts[1].strip()}" if len(parts) > 1 else None
            
            # Validate name
            name_result = check_package_name(name)
            if not name_result.is_valid:
                raise ValueError(f"Invalid package name: {name_result.message}")
                
            # Validate version spec if present
            if version_spec:
                try:
                    SpecifierSet(version_spec)
                except:
                    raise ValueError(f"Invalid version specifier: {version_spec}")
            
            return cls(name, version_spec, extras)
            
        except Exception as e:
            raise DependencyError(f"Failed to parse dependency '{dep_string}': {e}")

@dataclass
class ProjectMetadata:
    """Essential project metadata from pyproject.toml."""
    name: str
    version: str
    description: str
    requires_python: str
    dependencies: List[Dependency] = field(default_factory=list)
    dev_dependencies: List[Dependency] = field(default_factory=list)
    
    def validate(self) -> List[str]:
        """Validate metadata fields.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Validate name
        name_result = check_package_name(self.name)
        if not name_result.is_valid:
            errors.append(f"Invalid project name: {name_result.message}")
            
        # Validate version
        version_result = check_version(self.version)
        if not version_result.is_valid:
            errors.append(f"Invalid version: {version_result.message}")
            
        # Validate description
        if self.description:
            desc_result = validate_description(self.description)
            if not desc_result.is_valid:
                errors.append(f"Invalid description: {desc_result.message}")
                
        # Validate Python version
        try:
            SpecifierSet(self.requires_python)
        except Exception as e:
            errors.append(f"Invalid Python version requirement: {e}")
            
        return errors

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
            
            # Parse dependencies
            deps = [
                Dependency.from_string(d) 
                for d in project.get("dependencies", [])
            ]
            dev_deps = [
                Dependency.from_string(d) 
                for d in project.get("dev-dependencies", [])
            ]
            
            metadata = ProjectMetadata(
                name=project["name"],
                version=project.get("version", "0.1.0"),
                description=project.get("description", ""),
                requires_python=project.get("requires-python", ">=3.8"),
                dependencies=deps,
                dev_dependencies=dev_deps
            )
            
            # Validate metadata
            if errors := metadata.validate():
                raise InvalidProjectError("\n".join(errors))
                
            return metadata
            
        except KeyError as e:
            raise InvalidProjectError(f"Missing required field in pyproject.toml: {e}")
        except Exception as e:
            raise InvalidProjectError(f"Invalid project metadata: {e}")

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
            
        Raises:
            InvalidProjectError: If updates would make project invalid
        """
        if "project" not in self.data:
            self.data["project"] = {}
            
        updates = {}
        if version is not None:
            if not check_version(version).is_valid:
                raise InvalidProjectError(f"Invalid version: {version}")
            updates["version"] = version
            
        if description is not None:
            if not validate_description(description).is_valid:
                raise InvalidProjectError(f"Invalid description: {description}")
            updates["description"] = description
            
        if requires_python is not None:
            try:
                SpecifierSet(requires_python)
                updates["requires-python"] = requires_python
            except Exception as e:
                raise InvalidProjectError(f"Invalid Python version requirement: {e}")
                
        self.data["project"].update(updates)

    def add_dependency(
        self,
        package: str,
        version: Optional[str] = None,
        extras: Optional[Set[str]] = None,
        dev: bool = False
    ) -> None:
        """Add a package dependency.
        
        Args:
            package: Package name
            version: Optional version specifier
            extras: Optional package extras
            dev: Whether this is a development dependency
            
        Raises:
            DependencyError: If dependency is invalid
        """
        try:
            # Create dependency object for validation
            dep = Dependency(
                name=package,
                version_spec=f">={version}" if version else None,
                extras=extras or set()
            )
            
            if "project" not in self.data:
                self.data["project"] = {}
                
            dep_type = "dev-dependencies" if dev else "dependencies"
            if dep_type not in self.data["project"]:
                self.data["project"][dep_type] = []
                
            dep_str = str(dep)
            if dep_str not in self.data["project"][dep_type]:
                self.data["project"][dep_type].append(dep_str)
                
        except Exception as e:
            raise DependencyError(f"Failed to add dependency: {e}")

    def add_script(self, name: str, cmd: str) -> None:
        """Add a script entry point.
        
        Args:
            name: Script name
            cmd: Command to run
            
        Raises:
            PyProjectError: If script cannot be added
        """
        if "project" not in self.data:
            self.data["project"] = {}
        if "scripts" not in self.data["project"]:
            self.data["project"]["scripts"] = {}
            
        if not name.isidentifier():
            raise PyProjectError(f"Invalid script name: {name}")
            
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
            PyProjectError: If file cannot be saved
        """
        try:
            # Format with consistent indentation
            toml_str = toml.dumps(self.data)
            
            # Write atomically
            atomic_write(self.path, toml_str)
            
        except (FileError, toml.TomlDecodeError) as e:
            raise PyProjectError(f"Failed to save {self.path}: {e}")
    
    @classmethod
    def create_default(
        cls,
        path: Path,
        name: str,
        version: str = "0.1.0",
        description: str = "",
        python_version: str = ">=3.8"
    ) -> 'PyProject':
        """Create a new pyproject.toml with default settings.
        
        Args:
            path: Where to create the file
            name: Project name
            version: Project version
            description: Project description
            python_version: Required Python version
            
        Returns:
            New PyProject instance
            
        Raises:
            PyProjectError: If project cannot be created
        """
        # Validate inputs
        name_result = check_package_name(name)
        if not name_result.is_valid:
            raise PyProjectError(f"Invalid project name: {name_result.message}")
            
        version_result = check_version(version)
        if not version_result.is_valid:
            raise PyProjectError(f"Invalid version: {version_result.message}")
            
        if description and not validate_description(description).is_valid:
            raise PyProjectError(f"Invalid description: {description}")
            
        try:
            SpecifierSet(python_version)
        except Exception as e:
            raise PyProjectError(f"Invalid Python version requirement: {e}")
        
        project = cls(path)
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
