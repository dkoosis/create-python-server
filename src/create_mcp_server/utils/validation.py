"""Input validation utilities for MCP server creation.

This module provides validation functions for various inputs required
when creating an MCP server, such as:
- Package names (PEP 508)
- Version strings (PEP 440)
- File paths and permissions
- Project descriptions
- Configuration values
- Resource limits

File: create-mcp-server/utils/validation.py
"""

import logging
import os
import re
import string
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple, Union

from packaging.version import InvalidVersion, Version, parse

logger = logging.getLogger(__name__)

class ValidationResult(NamedTuple):
    """Result of a validation check."""
    is_valid: bool
    message: str
    details: Optional[Dict] = None

# Regular expressions for validation
PACKAGE_NAME_REGEX = re.compile(r'^[a-zA-Z0-9][-a-zA-Z0-9_.]*[a-zA-Z0-9]$')
URL_REGEX = re.compile(
    r'^https?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
    r'localhost|'  # localhost
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE
)
EMAIL_REGEX = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')

def check_package_name(name: str) -> ValidationResult:
    """Validate a Python package name against standard naming conventions.

    Args:
        name: The package name to validate

    Returns:
        ValidationResult with validation status and message

    Rules:
        - Must not be empty
        - Must contain only ASCII letters, digits, _, -, .  
        - Must not start/end with _, -, .
        - Must not contain spaces
        - Must be a valid Python identifier
        - Must be lowercase (recommendation only - warns but doesn't fail)
        - Must be between 2 and 100 characters
    """
    if not name:
        return ValidationResult(False, "Package name cannot be empty")

    if len(name) < 2:
        return ValidationResult(False, "Package name must be at least 2 characters")
        
    if len(name) > 100:
        return ValidationResult(False, "Package name must be under 100 characters")

    if " " in name:
        return ValidationResult(False, "Package name must not contain spaces")

    if not name.isascii():
        return ValidationResult(False, "Package name must contain only ASCII characters")

    allowed_chars = set(string.ascii_letters + string.digits + "-_.")
    if not all(c in allowed_chars for c in name):
        return ValidationResult(
            False,
            "Package name must contain only letters, digits, underscore, "
            "hyphen, and period"
        )

    if name.startswith(("_", "-", ".")) or name.endswith(("_", "-", ".")):
        return ValidationResult(
            False,
            "Package name must not start or end with underscore, hyphen, or period"
        )

    # Convert to Python package name format for additional checks
    package_name = name.replace("-", "_")
    if not package_name.isidentifier():
        return ValidationResult(
            False,
            "Package name must be a valid Python identifier when hyphens "
            "are converted to underscores"
        )

    # Check against regex pattern
    if not PACKAGE_NAME_REGEX.match(name):
        return ValidationResult(
            False,
            "Package name contains invalid characters or format"
        )

    # Warning for non-lowercase (but still valid)
    if not name.islower():
        logger.warning("Package name should be lowercase (but will be accepted)")

    return ValidationResult(True, "")

def check_version(version: str) -> ValidationResult:
    """Validate a version string against PEP 440.

    Args:
        version: The version string to validate

    Returns:
        ValidationResult with validation status and message
        
    Examples of valid versions:
        - 1.0.0
        - 2.1.0.dev1
        - 1.0b2
        - 1.0.0rc1
        - 1.0.0.post1
    """
    try:
        parsed = parse(version)
        return ValidationResult(
            True, 
            "",
            {'parsed_version': str(parsed)}
        )
    except InvalidVersion:
        return ValidationResult(
            False,
            f"Version '{version}' is not a valid semantic version (e.g. 1.0.0)"
        )

def check_project_path(path: Path) -> ValidationResult:
    """Validate a project path.

    Args:
        path: The project path to validate

    Returns:
        ValidationResult with validation status and message

    Checks:
        - Path must be absolute or able to be resolved
        - Parent directory must exist
        - Path must not exist or be an empty directory
        - Must have write permissions to parent directory
        - Path must not be too deep
        - Path must not contain invalid characters
    """
    try:
        resolved_path = path.resolve()
        parent = resolved_path.parent

        # Check path depth
        if len(resolved_path.parts) > 50:
            return ValidationResult(False, "Path is too deep")

        # Check parent directory
        if not parent.exists():
            return ValidationResult(False, f"Parent directory does not exist: {parent}")

        # Check if path exists
        if resolved_path.exists():
            if not resolved_path.is_dir():
                return ValidationResult(
                    False,
                    f"Path exists and is not a directory: {resolved_path}"
                )
            if any(resolved_path.iterdir()):
                return ValidationResult(
                    False,
                    f"Directory is not empty: {resolved_path}"
                )

        # Check write permissions
        if not os.access(parent, os.W_OK):
            return ValidationResult(
                False,
                f"No write permission for directory: {parent}"
            )

        # Check for reserved names
        reserved_names = {'con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3',
                         'com4', 'lpt1', 'lpt2', 'lpt3'}
        if path.name.lower() in reserved_names:
            return ValidationResult(False, f"'{path.name}' is a reserved name")

        return ValidationResult(True, "")

    except PermissionError as e:
        return ValidationResult(False, f"Permission error: {e}")
    except Exception as e:
        return ValidationResult(False, f"Invalid path: {e}")

def validate_description(description: str) -> ValidationResult:
    """Validate a project description.

    Args:
        description: The project description to validate

    Returns:
        ValidationResult with validation status and message

    Rules:
        - Must not be empty
        - Must not be too long (max 500 chars)
        - Must be mostly printable characters
        - Must not contain control characters
        - Should contain meaningful content
    """
    if not description:
        return ValidationResult(False, "Description cannot be empty")

    if len(description) > 500:
        return ValidationResult(False, "Description must be under 500 characters")

    if len(description) < 10:
        return ValidationResult(
            False,
            "Description should be at least 10 characters"
        )

    # Check for control characters
    if any(ord(c) < 32 for c in description):
        return ValidationResult(
            False,
            "Description must not contain control characters"
        )

    # Check for mostly printable characters (allow some whitespace)
    printable = set(string.printable)
    non_printable = [c for c in description if c not in printable]
    if len(non_printable) > len(description) * 0.1:  # Allow 10% non-printable
        return ValidationResult(
            False,
            "Description contains too many non-printable characters"
        )

    # Check for meaningful content
    words = description.split()
    if len(words) < 3:
        return ValidationResult(
            False,
            "Description should contain at least 3 words"
        )

    return ValidationResult(True, "")

def validate_url(url: str) -> ValidationResult:
    """Validate a URL string.

    Args:
        url: The URL to validate

    Returns:
        ValidationResult with validation status and message
    """
    if not url:
        return ValidationResult(False, "URL cannot be empty")

    if len(url) > 2000:
        return ValidationResult(False, "URL is too long")

    if not URL_REGEX.match(url):
        return ValidationResult(False, "Invalid URL format")

    return ValidationResult(True, "")

def validate_email(email: str) -> ValidationResult:
    """Validate an email address.

    Args:
        email: The email address to validate

    Returns:
        ValidationResult with validation status and message
    """
    if not email:
        return ValidationResult(False, "Email cannot be empty")

    if len(email) > 254:  # RFC 5321
        return ValidationResult(False, "Email is too long")

    if not EMAIL_REGEX.match(email):
        return ValidationResult(False, "Invalid email format")

    return ValidationResult(True, "")

def validate_resource_limits(
    memory_mb: int,
    cpu_percent: float,
    timeout_seconds: int
) -> ValidationResult:
    """Validate resource limits.

    Args:
        memory_mb: Maximum memory usage in MB
        cpu_percent: Maximum CPU usage percentage
        timeout_seconds: Maximum timeout in seconds

    Returns:
        ValidationResult with validation status and message
    """
    if memory_mb < 50 or memory_mb > 4096:
        return ValidationResult(False, "Memory limit must be between 50MB and 4GB")

    if cpu_percent < 0 or cpu_percent > 100:
        return ValidationResult(False, "CPU limit must be between 0 and 100")

    if timeout_seconds < 1 or timeout_seconds > 3600:
        return ValidationResult(False, "Timeout must be between 1 and 3600 seconds")

    return ValidationResult(True, "")