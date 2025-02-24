#!/bin/bash

# Set error handling
set -e  # Exit on any error
set -u  # Error on undefined variables

# --- Configuration ---
# This script resides in /Users/davidkoosis/projects/create_mcp_server
# It creates a *separate* project directory for the MCP server instance.

# Where the MCP *server instance* will be created (NOT where this script lives)
project_base_dir="/Users/davidkoosis/projects"  # Your main projects directory
project_dir="$project_base_dir/tmp/test_server"  # Specific server instance directory
venv_name="mcp_venv"
python_exe="python3"
# This script's location (automatically determined)
mcp_script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Where the mcp_server package is (same as where this script lives)
mcp_server_local_path="$mcp_script_dir"

# Colors for output
green='\033[0;32m'
red='\033[0;31m'
yellow='\033[0;33m'
no_color='\033[0m'

# Logging setup
log_file="$mcp_script_dir/setup.log"
error_log="$mcp_script_dir/setup_errors.log"

# --- Helper Functions ---

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${green}[SETUP]${no_color} $1"
    echo "[$timestamp] $1" >> "$log_file"
}

error() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${red}[ERROR]${no_color} $1" >&2
    echo "[$timestamp] ERROR: $1" >> "$error_log"
    if [ -f "$mcp_script_dir/check_imports_errors.txt" ]; then
        echo "Import check errors:" >> "$error_log"
        cat "$mcp_script_dir/check_imports_errors.txt" >> "$error_log"
    fi
    exit 1
}

warn() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${yellow}[WARNING]${no_color} $1"
    echo "[$timestamp] WARNING: $1" >> "$log_file"
}

cleanup() {
    if [ "${VIRTUAL_ENV:-}" != "" ]; then
        deactivate
    fi
    # Archive logs if there was an error
    if [ $? -ne 0 ]; then
        local archive_dir="$mcp_script_dir/logs/$(date '+%Y%m%d_%H%M%S')"
        mkdir -p "$archive_dir"
        [ -f "$log_file" ] && cp "$log_file" "$archive_dir/"
        [ -f "$error_log" ] && cp "$error_log" "$archive_dir/"
        [ -f "$mcp_script_dir/check_imports_errors.txt" ] && cp "$mcp_script_dir/check_imports_errors.txt" "$archive_dir/"
        warn "Logs archived to $archive_dir"
    fi
}
trap cleanup EXIT

# Initialize log files
mkdir -p "$(dirname "$log_file")"
touch "$log_file" "$error_log"
log "Starting setup process..."

# --- Core Functions ---

check_python_version() {
    if ! command -v "$python_exe" &> /dev/null; then
        error "Python interpreter '$python_exe' not found."
    fi
    # Check minimum Python version
    local min_version="3.10"
    local current_version=$("$python_exe" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    
    # Fix: Changed version comparison logic
    if printf '%s\n%s' "$min_version" "$current_version" | sort -C -V; then
        log "Python version check passed: $current_version"
    else
        error "Python version $min_version or higher required. Found version $current_version"
    fi
}

create_tmp_directory() {
    local base_dir="$1"
    local tmp_dir="$base_dir/tmp"
    if [ ! -d "$tmp_dir" ]; then
        log "Creating tmp directory at $tmp_dir"
        mkdir -p "$tmp_dir" || error "Failed to create tmp directory: $tmp_dir"
    fi
}

handle_existing_directory() {
    local dir="$1"
    if [ -d "$dir" ]; then
        read -p "Directory '$dir' exists. Remove and recreate? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log "Removing existing directory..."
            rm -rf "$dir"
        else
            error "Setup aborted by user."
        fi
    fi
}

create_project_directory() {
    local dir="$1"
    log "Creating project directory at $dir"
    mkdir -p "$dir"
    cd "$dir" || error "Failed to change directory to $dir"
}

create_and_activate_venv() {
    local venv_name="$1"
    log "Creating virtual environment..."
    "$python_exe" -m venv "$venv_name"
    . "$venv_name/bin/activate" || error "Failed to activate virtual environment"
    log "Virtual environment created and activated"
}

check_venv_activated() {
    if [ "${VIRTUAL_ENV:-}" = "" ] || [ "$(basename "${VIRTUAL_ENV:-}")" != "$venv_name" ]; then
        error "Virtual environment is not activated correctly."
    fi
    log "Virtual environment check passed"
}

upgrade_pip() {
    log "Upgrading pip..."
    python -m pip install --upgrade pip
}

install_mcp_server_local() {
    log "Installing mcp_server from local path: $mcp_server_local_path"
    pip install -e "$mcp_server_local_path" || error "Failed to install mcp_server"
    log "MCP server package installed successfully"
}

run_import_check() {
    log "Running import hygiene check..."
    local check_output
    check_output=$("$mcp_script_dir/check_imports.py" "$mcp_script_dir" 2>&1)
    local exit_code=$?
    
    echo "$check_output" > "$mcp_script_dir/check_imports_errors.txt"
    
    if [ $exit_code -ne 0 ]; then
        error "Import check failed! Details:\n$check_output"
    fi
    log "Import check passed"
}

create_mcp_server() {
    log "Creating new MCP server instance..."
    if ! python -m create_mcp_server init \
        --name "test_server" \
        --description "Test MCP Server" \
        --path "$project_dir"; then
        error "Failed to create MCP server"
    fi
    log "MCP server created successfully"
}

start_mcp_server() {
    log "Starting MCP server..."
    if ! python -m create_mcp_server start "$project_dir"; then
        error "Failed to start MCP server"
    fi
    log "MCP server started successfully"
}

# --- Main Script Execution ---
log "Starting MCP server setup..."

create_tmp_directory "$project_base_dir"
handle_existing_directory "$project_dir"
create_project_directory "$project_dir"
check_python_version
create_and_activate_venv "$venv_name"
check_venv_activated
upgrade_pip
install_mcp_server_local
run_import_check
create_mcp_server
start_mcp_server

log "Setup completed successfully!"
log "Virtual environment active: $project_dir/$venv_name"
log "Deactivate with: deactivate"