"""Setup utilities for MCP server creation and validation.

File: /Users/davidkoosis/projects/create_mcp_server/src/create_mcp_server/utils/setup.py

This module provides a high-level interface for creating and validating MCP server
projects. It consolidates functionality previously spread across shell scripts and
standalone Python files into a cohesive, maintainable package.

Key features:
- Project structure initialization
- Environment validation
- Virtual environment management
- Import hygiene checking 
- Logging and error tracking
- Automated cleanup on failure

Example:
    ```python
    from pathlib import Path
    from mcp.utils.setup import ProjectSetup

    setup = ProjectSetup(
        project_path=Path("./my_server"),
        name="my_server",
        version="0.1.0",
        description="Example MCP server"
    )

    try:
        setup.run()
    except SetupError as e:
        print(f"Setup failed: {e}")
    ```
"""

[Rest of the module implementation remains the same...]