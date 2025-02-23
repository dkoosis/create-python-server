import ast
import os
import argparse
import sys

def analyze_imports_in_file(file_path, project_root, found_errors):
    """Analyzes imports in a single Python file and suggests corrections."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
    except FileNotFoundError:
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        found_errors.append(file_path)
        return
    except Exception as e:
        print(f"ERROR: Could not read file {file_path}: {e}", file=sys.stderr)
        found_errors.append(file_path)
        return

    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        print(f"ERROR: Syntax error in {file_path}: {e}", file=sys.stderr)
        found_errors.append(file_path)
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in sys.builtin_module_names:
                    pass # Basic check for stdlib, can be expanded

        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:  # Absolute import
                if node.module not in sys.builtin_module_names:
                    pass # Could check if module is installed, but it slows down

            else:  # Relative import
                current_dir = os.path.dirname(file_path)
                relative_path_parts = [".."] * (node.level - 1)
                if node.module:
                    relative_path_parts.extend(node.module.split("."))
                full_relative_path = os.path.join(current_dir, *relative_path_parts)

                try:
                    absolute_path = os.path.abspath(full_relative_path)

                    if os.path.isfile(absolute_path + ".py"):
                        absolute_path += ".py"
                    elif os.path.isfile(absolute_path + ".pyc"):
                        absolute_path += ".pyc"
                    elif os.path.isdir(absolute_path):
                        if not os.path.isfile(os.path.join(absolute_path, "__init__.py")):
                            print(f"WARNING: In '{file_path}', line {node.lineno}: Relative import refers to a package without '__init__.py'.", file=sys.stderr)
                            # Consider this a warning, not a fatal error
                    else:
                        # Attempt to suggest a correction
                        suggested_import = suggest_correction(file_path, project_root, node)
                        print(f"ERROR: In '{file_path}', line {node.lineno}: Could not resolve relative import.", file=sys.stderr)
                        if suggested_import:
                             print(f"       Perhaps try: {suggested_import}", file=sys.stderr)
                        else:
                             print(f"       No suggestion available.", file=sys.stderr)

                        found_errors.append(file_path)
                except Exception as e:
                    print(f"ERROR: In '{file_path}', line {node.lineno}: Could not resolve relative import: {e}", file=sys.stderr)
                    found_errors.append(file_path)


def suggest_correction(file_path, project_root, import_node):
    """Attempts to suggest a correct import statement."""

    current_dir = os.path.dirname(file_path)
    imported_names = [alias.name for alias in import_node.names]

    # 1. Construct the *intended* target directory based on the faulty relative import.
    target_dir_parts = [".."] * (import_node.level - 1)
    if import_node.module:
        target_dir_parts.extend(import_node.module.split("."))
    target_dir = os.path.abspath(os.path.join(current_dir, *target_dir_parts))

    # 2.  If the target *would have been* a file (not a package), try to find a matching file
    #     in the project, starting from the project root.
    if not os.path.isdir(target_dir):  #If not directory, it must be trying to be a file
      target_file_base = os.path.basename(target_dir) #last part of intended path
      for root, _, files in os.walk(project_root):
        for file in files:
            if file.startswith(target_file_base) and file.endswith((".py",".pyc")): #Find the file
                #Calculate *correct* relative path from the file_path to candidate
                correct_rel_path = os.path.relpath(os.path.join(root, file[:-3]), current_dir) #Path to thing we want to import

                #Build the 'from ... import ...' statement
                parts = correct_rel_path.split(os.sep)
                level = 0
                module_part = ""

                if parts[0] == ".": #Starts same dir
                    level = 1
                    module_part = ".".join(parts[1:]) #All but the first

                elif ".." in parts:
                    level = parts.count("..") + 1 #Count .. plus from current dir
                    module_part = ".".join(parts[level-1:])

                else: #Absolute import
                    level = 0
                    module_part = ".".join(parts)

                from_statement = f"from {'.'*level}{module_part} import {', '.join(imported_names)}"
                return from_statement

    # 3. If the target *is* a package, check if __init__.py, if it exists suggest the correct path
    elif os.path.isdir(target_dir) and os.path.isfile(os.path.join(target_dir, "__init__.py")):
        correct_rel_path = os.path.relpath(target_dir, current_dir)
        parts = correct_rel_path.split(os.sep)
        level = 0
        module_part = ""

        if parts[0] == ".":  # Starts same dir
            level = 1
            module_part = ".".join(parts[1:])  # All but the first

        elif ".." in parts:
            level = parts.count("..") + 1  # Count .. plus from current dir
            module_part = ".".join(parts[level - 1:])
        else:
            level=0
            module_part = ".".join(parts)

        from_statement = f"from {'.'*level}{module_part} import {', '.join(imported_names)}"
        return from_statement

    return None  # No suggestion found



def analyze_project(project_root):
    """Recursively analyzes all Python files in a project."""
    found_errors = []
    for root, _, files in os.walk(project_root):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                analyze_imports_in_file(file_path, project_root, found_errors)

    if found_errors:
        print("\nImport hygiene check FAILED. See errors above.")
        sys.exit(1)
    else:
        print("\nImport hygiene check passed. No issues found.")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Check import hygiene in a Python project.")
    parser.add_argument("project_root", nargs="?", default=".", help="The root directory of the project (default: current directory)")
    args = parser.parse_args()

    analyze_project(os.path.abspath(args.project_root)) # Use absolute path for project root

if __name__ == "__main__":
    main()