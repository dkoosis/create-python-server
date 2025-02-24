"""File system utilities for safe file operations.

This module provides robust utilities for file system operations with:
- Atomic file writes
- Safe directory removal
- File and directory permission handling
- Resource cleanup
- Lock file management

File: create_mcp_server/utils/files.py
"""

import errno
import fcntl
import logging
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator, Optional, Union, cast

logger = logging.getLogger(__name__)

class FileError(Exception):
    """Base exception for file operations."""
    pass

class LockError(FileError):
    """Raised when file locking fails."""
    pass

class PermissionError(FileError):
    """Raised when permission operations fail."""
    pass

class AtomicWriteError(FileError):
    """Raised when atomic write operations fail."""
    pass

@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Create an exclusive file lock.
    
    Args:
        path: Path to lock file
        
    Raises:
        LockError: If lock cannot be acquired
    """
    lock_path = path.with_suffix('.lock')
    lock_fd = None
    
    try:
        # Open or create lock file
        lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
        
        # Try to acquire exclusive lock
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EAGAIN):
                raise LockError(f"File {path} is locked by another process")
            raise
            
        yield
        
    except Exception as e:
        if not isinstance(e, LockError):
            raise FileError(f"Lock operation failed: {e}")
        raise
        
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
                lock_path.unlink(missing_ok=True)
            except OSError as e:
                logger.warning(f"Failed to cleanup lock file: {e}")

def atomic_write(path: Path, content: Union[str, bytes]) -> None:
    """Write content to file atomically using a temporary file.
    
    Args:
        path: Target file path
        content: Content to write (string or bytes)
        
    Raises:
        AtomicWriteError: If write operation fails
    """
    # Ensure parent directory exists
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise AtomicWriteError(f"Failed to create directory {path.parent}: {e}")

    # Create temporary file in same directory
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f'.{path.name}.',
        suffix='.tmp'
    )
    tmp_path = Path(tmp_path)
    
    try:
        with file_lock(path):
            # Write content to temporary file
            try:
                if isinstance(content, str):
                    content_bytes = content.encode('utf-8')
                else:
                    content_bytes = content
                    
                os.write(tmp_fd, content_bytes)
                os.fsync(tmp_fd)
            finally:
                os.close(tmp_fd)

            # Set permissions to match target or default
            if path.exists():
                shutil.copymode(str(path), str(tmp_path))
            else:
                tmp_path.chmod(0o644)

            # Atomic rename
            tmp_path.replace(path)
            
    except Exception as e:
        # Clean up temp file
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise AtomicWriteError(f"Failed to write {path}: {e}")

def safe_rmtree(
    path: Path,
    ignore_errors: bool = False,
    ignore_read_only: bool = True
) -> None:
    """Safely remove a directory tree.
    
    Args:
        path: Directory to remove
        ignore_errors: Whether to ignore errors
        ignore_read_only: Whether to remove read-only files
        
    This is safer than shutil.rmtree() because it:
    - Handles permission errors gracefully
    - Retries on failure
    - Only removes what it should
    - Uses proper error handling
    """
    if not path.exists():
        return
        
    def handle_error(func: callable, fpath: str, exc_info: tuple) -> None:
        """Error handler for removing read-only files."""
        if not ignore_errors:
            err_type, err_inst, traceback = exc_info
            
            # Handle read-only files
            if (
                isinstance(err_inst, OSError) and 
                err_inst.errno == errno.EACCES and
                ignore_read_only
            ):
                try:
                    os.chmod(fpath, stat.S_IWRITE)
                    func(fpath)
                    return
                except OSError as e:
                    logger.warning(f"Failed to remove read-only file {fpath}: {e}")
                    
            # Re-raise other errors
            raise err_type(err_inst).with_traceback(traceback)
            
    try:
        shutil.rmtree(
            path,
            ignore_errors=ignore_errors,
            onerror=handle_error
        )
    except Exception as e:
        if not ignore_errors:
            raise FileError(f"Failed to remove directory tree {path}: {e}")
        logger.warning(f"Error removing directory tree {path}: {e}")

def safe_copy(
    src: Path,
    dst: Path,
    follow_symlinks: bool = True
) -> None:
    """Safely copy a file with proper error handling.
    
    Args:
        src: Source file path
        dst: Destination file path
        follow_symlinks: Whether to follow symbolic links
        
    Raises:
        FileError: If copy operation fails
    """
    try:
        # Ensure parent directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file with metadata
        shutil.copy2(
            str(src),
            str(dst),
            follow_symlinks=follow_symlinks
        )
    except Exception as e:
        raise FileError(f"Failed to copy {src} to {dst}: {e}")

def ensure_directory(
    path: Path,
    mode: int = 0o755,
    parents: bool = True
) -> None:
    """Ensure a directory exists with proper permissions.
    
    Args:
        path: Directory path
        mode: Directory permissions
        parents: Whether to create parent directories
        
    Raises:
        FileError: If directory cannot be created
    """
    try:
        path.mkdir(mode=mode, parents=parents, exist_ok=True)
    except Exception as e:
        raise FileError(f"Failed to create directory {path}: {e}")

def make_executable(path: Path) -> None:
    """Make a file executable.
    
    Args:
        path: Path to file
        
    Raises:
        PermissionError: If permissions cannot be set
    """
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception as e:
        raise PermissionError(f"Failed to make {path} executable: {e}")

@contextmanager
def atomic_replace(path: Path) -> Iterator[Path]:
    """Context manager for atomic file replacement.
    
    Args:
        path: Path to file to replace
        
    Yields:
        Path to temporary file
        
    The temporary file will be moved to the target path on success,
    or deleted on failure.
    """
    temp_path = path.with_suffix(f'.{os.getpid()}.tmp')
    try:
        with file_lock(path):
            yield temp_path
            if temp_path.exists():
                temp_path.replace(path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass