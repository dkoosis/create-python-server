"""Tests for the setup module.

File: /Users/davidkoosis/projects/create_mcp_server/tests/utils/test_setup.py

This module contains tests for the project setup functionality, covering:
- Project initialization
- Environment validation
- Import checking
- Error handling and cleanup
- Logging configuration
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, patch

import pytest

from create_mcp_server.utils.setup import ProjectSetup, SetupError, ImportChecker, ImportIssue

# Test fixtures
@pytest.fixture
def temp_project_dir(tmp_path) -> Generator[Path, None, None]:
    """Provide a temporary project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    yield project_dir
    # Cleanup
    if project_dir.exists():
        shutil.rmtree(project_dir)

@pytest.fixture
def setup_instance(temp_project_dir: Path) -> ProjectSetup:
    """Provide a ProjectSetup instance."""
    return ProjectSetup(
        project_path=temp_project_dir,
        name="test_project",
        version="0.1.0",
        description="Test MCP Server"
    )

# Environment validation tests
def test_validate_environment_python_version(setup_instance: ProjectSetup):
    """Test Python version validation."""
    # Mock Python version
    with patch('sys.version_info', (3, 7)):
        errors = setup_instance.validate_environment()
        assert any("Python 3.10 or higher required" in err for err in errors)

    with patch('sys.version_info', (3, 10)):
        errors = setup_instance.validate_environment()
        assert not any("Python" in err for err in errors)

def test_validate_environment_project_path(setup_instance: ProjectSetup, tmp_path: Path):
    """Test project path validation."""
    # Test non-existent parent directory
    setup_instance.project_path = tmp_path / "nonexistent" / "project"
    errors = setup_instance.validate_environment()
    assert any("Parent directory does not exist" in err for err in errors)

    # Test valid path
    valid_dir = tmp_path / "valid"
    valid_dir.mkdir()
    setup_instance.project_path = valid_dir / "project"
    errors = setup_instance.validate_environment()
    assert not any("directory" in err for err in errors)

def test_validate_environment_uv_installed(setup_instance: ProjectSetup):
    """Test UV package manager check."""
    with patch('create_mcp_server.utils.setup.ensure_uv_installed') as mock_ensure:
        mock_ensure.side_effect = Exception("UV not found")
        errors = setup_instance.validate_environment()
        assert any("UV package manager" in err for err in errors)

        mock_ensure.side_effect = None
        errors = setup_instance.validate_environment()
        assert not any("UV package manager" in err for err in errors)

# Project initialization tests
def test_initialize_project_structure(setup_instance: ProjectSetup):
    """Test project directory structure creation."""
    setup_instance.initialize_project()
    
    # Check essential directories
    assert setup_instance.package_dir.exists()
    assert setup_instance.log_dir.exists()
    assert setup_instance.venv_dir.exists()
    
    # Check pyproject.toml
    pyproject_path = setup_instance.project_path / "pyproject.toml"
    assert pyproject_path.exists()

def test_initialize_project_dependencies(setup_instance: ProjectSetup):
    """Test dependency installation."""
    with patch('create_mcp_server.utils.setup.run_uv_command') as mock_run:
        setup_instance.initialize_project()
        
        # Check venv creation call
        venv_call = mock_run.call_args_list[0]
        assert "venv" in venv_call[0][0]
        
        # Check pip install call
        pip_call = mock_run.call_args_list[1]
        assert "pip" in pip_call[0][0]
        assert "install" in pip_call[0][0]

def test_initialize_project_error_handling(setup_instance: ProjectSetup):
    """Test error handling during initialization."""
    with patch('create_mcp_server.utils.setup.run_uv_command') as mock_run:
        mock_run.side_effect = Exception("Installation failed")
        
        with pytest.raises(SetupError) as exc_info:
            setup_instance.initialize_project()
        
        assert "Installation failed" in str(exc_info.value)
        assert setup_instance.log_dir.exists()  # Logs should be preserved

# Import checking tests
def test_import_checker_basic(temp_project_dir: Path):
    """Test basic import checking functionality."""
    checker = ImportChecker(temp_project_dir)
    
    # Create test file with imports
    test_file = temp_project_dir / "test.py"
    test_file.write_text("""
    from . import module
    from .. import other
    import *  # Bad practice
    """)
    
    checker.check_file(test_file)
    issues = checker.issues
    
    assert any(issue.message == "Wildcard imports are discouraged" for issue in issues)
    assert any("relative import" in issue.message.lower() for issue in issues)

def test_import_checker_valid_imports(temp_project_dir: Path):
    """Test checker with valid imports."""
    checker = ImportChecker(temp_project_dir)
    
    # Create valid test file
    test_file = temp_project_dir / "valid.py"
    test_file.write_text("""
    import os
    import sys
    from pathlib import Path
    """)
    
    checker.check_file(test_file)
    assert not checker.issues

# Logging tests
def test_logging_setup(setup_instance: ProjectSetup):
    """Test logging configuration."""
    with patch('logging.FileHandler') as mock_file_handler:
        setup_instance._setup_logging()
        
        # Check log file creation
        mock_file_handler.assert_called_once()
        log_path = mock_file_handler.call_args[0][0]
        assert log_path.parent == setup_instance.log_dir

def test_logging_archive(setup_instance: ProjectSetup):
    """Test log archival functionality."""
    # Create some test logs
    setup_instance.log_dir.mkdir(exist_ok=True)
    test_log = setup_instance.log_dir / "test.log"
    test_log.write_text("test log content")
    
    # Test archival
    setup_instance._archive_logs(error=True)
    
    # Check archive creation
    archives = list(setup_instance.log_dir.glob("*_error"))
    assert len(archives) == 1
    assert (archives[0] / "test.log").exists()

# Integration tests
def test_full_setup_process(setup_instance: ProjectSetup):
    """Test the complete setup process."""
    with patch('create_mcp_server.utils.setup.ensure_uv_installed'), \
         patch('create_mcp_server.utils.setup.run_uv_command'):
        
        setup_instance.run()
        
        # Check project structure
        assert setup_instance.package_dir.exists()
        assert setup_instance.venv_dir.exists()
        assert (setup_instance.project_path / "pyproject.toml").exists()
        
        # Check logs
        assert setup_instance.log_dir.exists()
        assert any(setup_instance.log_dir.glob("*.log"))

def test_setup_cleanup_on_error(setup_instance: ProjectSetup):
    """Test cleanup when setup fails."""
    with patch('create_mcp_server.utils.setup.ensure_uv_installed') as mock_ensure:
        mock_ensure.side_effect = Exception("Setup failed")
        
        with pytest.raises(SetupError):
            setup_instance.run()
        
        # Check error logs are preserved
        assert setup_instance.log_dir.exists()
        error_archives = list(setup_instance.log_dir.glob("*_error"))
        assert len(error_archives) == 1
