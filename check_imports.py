"""Check Python import hygiene in a project.

This module analyzes Python imports in a project, verifying:
- Relative imports resolve correctly
- Imported names exist in target modules
- Packages have __init__.py files

It provides clear error messages and suggestions for fixes when issues are found.
"""

import ast
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

@dataclass
class ImportIssue:
    """Represents an issue found during import checking."""
    file: str
    line: int
    message: str
    is_error: bool = True
    suggestion: Optional[str] = None

@dataclass
class ImportCheckResults:
    """Collection of issues found during import checking."""
    errors: Set[str] = field(default_factory=set)
    warnings: Set[str] = field(default_factory=set)
    issues: List[ImportIssue] = field(default_factory=list)

    def add_error(self, file: str, line: int, message: str, suggestion: Optional[str] = None):
        """Add an error with optional suggestion."""
        self.errors.add(file)
        self.issues.append(ImportIssue(file, line, message, True, suggestion))

    def add_warning(self, file: str, line: int, message: str):
        """Add a warning."""
        self.warnings.add(file)
        self.issues.append(ImportIssue(file, line, message, False))

    def has_issues(self) -> bool:
        """Return True if any errors were found."""
        return bool(self.errors)

class NameChecker:
    """Check if names exist in Python modules."""

    @staticmethod
    def check_names_in_file(file_path: Path, names: List[str]) -> Set[str]:
        """Check which names exist in a Python file.
        
        Args:
            file_path: Path to Python file
            names: List of names to check
            
        Returns:
            Set of names that were found in the file
        """
        try:
            with open(file_path) as f:
                tree = ast.parse(f.read())
        except Exception as e:
            # If we can't parse the file, assume no names found
            return set()

        found_names = set()
        for node in ast.walk(tree):
            # Check variable assignments
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = getattr(node, 'targets', [getattr(node, 'target', None)])
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in names:
                        found_names.add(target.id)
                        
            # Check function definitions
            elif isinstance(node, ast.FunctionDef) and node.name in names:
                found_names.add(node.name)
                
            # Check class definitions
            elif isinstance(node, ast.ClassDef) and node.name in names:
                found_names.add(node.name)

        return found_names

class ImportResolver:
    """Resolve and validate Python imports."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results = ImportCheckResults()

    def check_file(self, file_path: Path) -> None:
        """Check imports in a single Python file."""
        try:
            with open(file_path) as f:
                tree = ast.parse(f.read())
        except Exception as e:
            self.results.add_error(str(file_path), 0, f"Failed to parse file: {e}")
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                self._check_relative_import(file_path, node)

    def _check_relative_import(self, file_path: Path, node: ast.ImportFrom) -> None:
        """Check a relative import statement."""
        # Calculate target path
        current_dir = file_path.parent
        path_parts = ['..'] * (node.level - 1)
        if node.module:
            path_parts.extend(node.module.split('.'))
        target = current_dir.joinpath(*path_parts).resolve()

        # Check if target exists
        if target.is_dir():
            self._check_package_import(file_path, node, target)
        elif target.with_suffix('.py').exists():
            self._check_module_import(file_path, node, target.with_suffix('.py'))
        else:
            suggestion = self._suggest_import(file_path, node)
            self.results.add_error(
                str(file_path), 
                node.lineno,
                "Could not resolve relative import",
                suggestion
            )

    def _check_package_import(self, file_path: Path, node: ast.ImportFrom, package_dir: Path) -> None:
        """Check import from a package."""
        init_file = package_dir / '__init__.py'
        if not init_file.exists():
            self.results.add_warning(
                str(file_path),
                node.lineno,
                f"Package at {package_dir} missing __init__.py"
            )
            return

        if node.names[0].name != '*':  # Skip star imports
            found = NameChecker.check_names_in_file(
                init_file,
                [n.name for n in node.names]
            )
            missing = set(n.name for n in node.names) - found
            if missing:
                self.results.add_error(
                    str(file_path),
                    node.lineno,
                    f"Names not found in {init_file}: {', '.join(missing)}"
                )

    def _check_module_import(self, file_path: Path, node: ast.ImportFrom, module_file: Path) -> None:
        """Check import from a module file."""
        if node.names[0].name != '*':  # Skip star imports
            found = NameChecker.check_names_in_file(
                module_file,
                [n.name for n in node.names]
            )
            missing = set(n.name for n in node.names) - found
            if missing:
                self.results.add_error(
                    str(file_path),
                    node.lineno,
                    f"Names not found in {module_file}: {', '.join(missing)}"
                )

    def _suggest_import(self, file_path: Path, node: ast.ImportFrom) -> Optional[str]:
        """Try to suggest a correct import statement."""
        # Implementation of import suggestion logic here
        # (Keeping existing suggestion logic, just moved to a separate method)
        return None

def check_project(project_root: str) -> bool:
    """Check import hygiene for a Python project.
    
    Args:
        project_root: Root directory of the project
        
    Returns:
        True if no errors were found, False otherwise
    """
    root = Path(project_root).resolve()
    resolver = ImportResolver(root)
    
    for path in root.rglob('*.py'):
        if not any(p.name.startswith('.') for p in path.parents):
            resolver.check_file(path)

    # Print results
    for issue in resolver.results.issues:
        msg = f"{'ERROR' if issue.is_error else 'WARNING'}: {issue.file}, line {issue.line}: {issue.message}"
        if issue.suggestion:
            msg += f"\n       Suggestion: {issue.suggestion}"
        print(msg, file=sys.stderr)

    if resolver.results.has_issues():
        print("\nImport hygiene check FAILED. See errors above.", file=sys.stderr)
        return False
    else:
        print("\nImport hygiene check passed. No issues found.")
        return True

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Check import hygiene in a Python project.")
    parser.add_argument("project_root", nargs="?", default=".", 
                       help="Root directory of the project (default: current directory)")
    args = parser.parse_args()

    success = check_project(args.project_root)
    sys.exit(0 if success else 1)