# Create MCP Server

A tool for creating new Model Context Protocol servers.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/dkoosis/create-python-server
cd create-python-server

# Run the setup script
./setup.sh

# Create your first MCP server
create_mcp_server
```

## Manual Setup

If you prefer to set up manually:

1. Create and activate virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install in editable mode:
   ```bash
   pip install -e .
   ```

## Troubleshooting

If you encounter "command not found: create_mcp_server":
- Ensure you're in the virtual environment (you should see (.venv) in your prompt)
- Try reinstalling the package: `pip install -e .`
- You can also run directly as a module: `python -m create_mcp_server`

## Development

After making changes to the code:
1. Ensure you're in the virtual environment
2. Reinstall the package: `pip install -e .`