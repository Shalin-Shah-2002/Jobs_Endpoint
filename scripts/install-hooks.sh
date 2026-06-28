#!/usr/bin/env bash
# Install git hooks that auto-log to Second Brain vault
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$SCRIPT_DIR/hooks"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GIT_HOOKS="$REPO_ROOT/.git/hooks"

if [ ! -d "$REPO_ROOT/.git" ]; then
	echo "ERROR: No .git directory found. Run 'git init' first."
	exit 1
fi

mkdir -p "$GIT_HOOKS"

install_hook() {
	local name="$1"
	cp "$HOOKS_DIR/$name" "$GIT_HOOKS/$name"
	chmod +x "$GIT_HOOKS/$name"
	echo "  Installed: $name"
}

echo "Installing hooks for jobs-endpoint..."
install_hook "post-commit"
install_hook "post-merge"
echo "Done. Hooks will now auto-log to:"
echo "  Vault → 09_Logs/CodingSessions/"
