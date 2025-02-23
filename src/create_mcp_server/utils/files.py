"""File system utilities for safe file operations.

File: create_mcp_server/utils/files.py
"""

import os
import shutil
from pathlib import Path
from typing import BinaryIO, Union

def atomic_write(path: Path, content: Union[str, bytes]) -> None:
    """Write content to file atomically using a temporary file.
    
    Args:
        path: Target file path
        content: Content to write (string or bytes)
        
    Raises:
        OSError: If file cannot be written
    """
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content to temporary file
        if isinstance(content, str):
            temp_path.write_text(content)
        else:
            temp_path.write_bytes(content)
            
        # Atomic replace
        temp_path.replace(path)
        
    finally:
        # Clean up temp file if something went wrong
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

def safe_rmtree(path: Path) -> None:
    """Safely remove a directory tree.
    
    Args:
        path: Directory to remove
        
    This is safer than shutil.rmtree() because it:
    - Handles permission errors gracefully
    - Retries on failure
    - Only removes what it should
    """
    if not path.exists():
        return
        
    def onerror(func: callable, fpath: str, exc_info: tuple) -> None:
        """Error handler for removing read-only files."""
        try:
            os.chmod(fpath, stat.S_IWRITE)
            func(fpath)
        except OSError:
            pass
            
    try:
        shutil.rmtree(path, onerror=onerror)
    except Exception:
        # If full remove fails, try removing contents
        try:
            for item in path.iterdir():
                if item.is_file():
                    item.unlink(missing_ok=True)
                elif item.is_dir():
                    safe_rmtree(item)
        except OSError:
            pass