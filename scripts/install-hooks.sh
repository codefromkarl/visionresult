#!/usr/bin/env bash
# ==============================================================================
# Install Git Hooks — Visual Insight Agent
# ==============================================================================
# 将 scripts/ 中的 hook 脚本链接到 .git/hooks/
#
# Usage:
#   bash scripts/install-hooks.sh
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"

echo "📦 Installing git hooks..."
echo "   Source: $SCRIPT_DIR"
echo "   Target: $HOOKS_DIR"
echo ""

# 确保 hooks 目录存在
mkdir -p "$HOOKS_DIR"

# 安装 pre-commit hook
if [[ -f "$SCRIPT_DIR/pre-commit" ]]; then
    ln -sf "../../scripts/pre-commit" "$HOOKS_DIR/pre-commit"
    echo "  ✅ pre-commit hook installed"
else
    echo "  ⚠️  scripts/pre-commit not found"
fi

echo ""
echo "✅ Git hooks installed!"
echo ""
echo "The pre-commit hook will run automatically before each commit."
echo "To bypass: git commit --no-verify"
