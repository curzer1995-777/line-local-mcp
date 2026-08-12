#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "Installing LINE Local MCP..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install "$SCRIPT_DIR"

echo
echo "Checking access to local LINE history..."
if ! "$VENV_DIR/bin/line-local-mcp" --doctor; then
  echo
  echo "A one-time LINE key setup is required."
  "$VENV_DIR/bin/line-local-mcp" --setup-key
  "$VENV_DIR/bin/line-local-mcp" --doctor
fi

echo
echo "LINE Local MCP is ready."
echo "MCP command: $VENV_DIR/bin/line-local-mcp"
echo
echo "Keep this folder in place after connecting it to your AI client."
