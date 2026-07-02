"""Wrapper script to launch the PETEX MCP Server via stdio."""
import sys
import os

# Ensure the project is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from petex_mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
