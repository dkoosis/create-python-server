"""Input validation utilities for MCP server creation.

This module provides validation functions for various inputs required
when creating an MCP server, such as package names, versions, etc.

Validation rules follow Python packaging standards (PEP 508, PEP 440)
and common best practices for project naming.

File: create_mcp_server/utils/validation.py
"""

import os
import re
from pathlib import Path
from typing import Tuple

import click
from packaging.version import InvalidVersion, parse

def check_package_name(name: str) -> Tuple[bool, str]:
    """Validate a Python package name against standard naming conventions.

    Args:
        name: The package name to validate

    Returns:
        A tuple of (is_valid, error_message). If valid, error_message is empty.
        If invalid, error_message contains the reason.

    Rules:
        - Must not be empty
        - Must contain only ASCII letters, digits, _, -, .  
        - Must not start/end with _, -, .
        - Must not contain spaces
        - Must be a valid Python identifier
        - Must be lowercase (recommendation only - warns but doesn't fail)
    """
    if not name:
        return False, "Project name cannot be empty"

    if " " in name:
        return False, "Project name must not contain spaces"

    if not name.isascii():
        return False, "Project name must contain only ASCII characters"

    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not all(c in allowed_chars for c in name):
        return False, "Project name must contain only letters, digits, underscore, hyphen, and period"

    if name.startswith(("_", "-", ".")) or name.endswith(("_", "-", ".")):
        return False, "Project name must not start or end with underscore, hyphen, or period"

    # Convert to Python package name format for additional checks
    package_name = name.replace("-", "_")
    if not package_name.isidentifier():
        return False, "Project name must be a valid Python identifier when hyphens are converted to underscores"

    # Warning for non-lowercase (but still valid)
    if not name.islower():
        click.echo("Warning: Project name should be lowercase (but will be accepted)", err=True)

    return True, ""

def check_version(version: str) -> Tuple[bool, str]:
    """Validate a version string against PEP 440.

    Args:
        version: The version string to validate

    Returns:
        A tuple of (is_valid, error_message). If valid, error_message is empty.
        If invalid, error_message contains the reason.
    """
    try:
        parse(version)
        return True, ""
    except InvalidVersion:
        return False, f"Version '{version}' is not a valid semantic version (e.g. 1.0.0)"

def check_project_path(path: Path) -> Tuple[bool, str]:
    """Validate a project path.

    Args:
        path: The project path to validate

    Returns:
        A tuple of (is_valid, error_message). If valid, error_message is empty.
        If invalid, error_message contains the reason.

    Checks:
        - Path must be absolute or able to be resolved
        - Parent directory must exist
        - Path must not exist or be an empty directory
        - Must have write permissions to parent directory
    """
    try:
        resolved_path = path.resolve()
        parent = resolved_path.parent

        if not parent.exists():
            return False, f"Parent directory does not exist: {parent}"

        if resolved_path.exists():
            if not resolved_path.is_dir():
                return False, f"Path exists and is not a directory: {resolved_path}"
            if any(resolved_path.iterdir()):
                return False, f"Directory is not empty: {resolved_path}"

        # Check write permissions on parent
        if not os.access(parent, os.W_OK):
            return False, f"No write permission for directory: {parent}"

        return True, ""

    except PermissionError as e:
        return False, f"Permission error: {e}"
    except Exception as e:
        return False, f"Invalid path: {e}"

def validate_description(description: str) -> Tuple[bool, str]:
    """Validate a project description.

    Args:
        description: The project description to validate

    Returns:
        A tuple of (is_valid, error_message). If valid, error_message is empty.
        If invalid, error_message contains the reason.

    Rules:
        - Must not be empty
        - Must not be too long (max 500 chars)
        - Must be mostly printable characters
    """
    if not description:
        return False, "Description cannot be empty"

    if len(description) > 500:
        return False, "Description must be under 500 characters"

    # Check for mostly printable characters (allow some whitespace)
    printable = set(string.printable)
    non_printable = [c for c in description if c not in printable]
    if len(non_printable) > len(description) * 0.1:  # Allow 10% non-printable
        return False, "Description contains too many non-printable characters"

    return True, ""

def print_validation_error(error_msg: str) -> None:
    """Print a validation error message in a consistent format.

    Args:
        error_msg: The error message to print
    """
    click.echo(f"❌ {error_msg}", err=True)
