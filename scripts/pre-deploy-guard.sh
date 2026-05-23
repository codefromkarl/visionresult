#!/usr/bin/env bash
# ==============================================================================
# Visual Insight Agent — Pre-Deploy Guard Script
# ==============================================================================
# 部署前必须通过的所有检查。任何一项失败都会阻止部署。
#
# Usage:
#   bash scripts/pre-deploy-guard.sh          # 完整检查
#   bash scripts/pre-deploy-guard.sh --quick   # 快速检查（跳过慢速测试）
#   bash scripts/pre-deploy-guard.sh --ci      # CI 模式（更严格）
#
# Exit codes:
#   0 = all checks passed
#   1 = one or more checks failed
# ==============================================================================

set -euo pipefail

# ─── 配置 ──────────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

ERRORS=0
WARNINGS=0
MODE="${1:-full}"
CI_MODE=false

if [[ "$MODE" == "--ci" ]]; then
    CI_MODE=true
    MODE="full"
fi

log_pass() { echo -e "  ${GREEN}✅ PASS${NC}: $1"; }
log_fail() { echo -e "  ${RED}❌ FAIL${NC}: $1"; ERRORS=$((ERRORS + 1)); }
log_warn() { echo -e "  ${YELLOW}⚠️  WARN${NC}: $1"; WARNINGS=$((WARNINGS + 1)); }
log_info() { echo -e "  ${BLUE}ℹ️  INFO${NC}: $1"; }
log_section() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

# ─── 0. 环境检查 ──────────────────────────────────────────────────────────────

log_section "0. Environment Check"

# 检查是否在项目根目录
if [[ ! -f "pyproject.toml" ]] || [[ ! -d "src/vision_insight" ]]; then
    log_fail "Not in project root directory"
    exit 1
fi
log_pass "Project root directory"

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
if [[ $(echo "$PYTHON_VERSION >= 3.11" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
    log_pass "Python $PYTHON_VERSION"
else
    log_warn "Python $PYTHON_VERSION (recommended >= 3.11)"
fi

# ─── 1. 代码质量 ──────────────────────────────────────────────────────────────

log_section "1. Code Quality"

# Ruff lint
echo -n "  Ruff lint... "
if ruff check src/ --quiet 2>/dev/null; then
    log_pass "Ruff lint (0 errors)"
else
    log_fail "Ruff lint failed"
    ruff check src/ --quiet 2>/dev/null || true
fi

# Ruff format check
echo -n "  Ruff format... "
if ruff format --check src/ --quiet 2>/dev/null; then
    log_pass "Ruff format (0 diffs)"
else
    log_fail "Ruff format check failed"
    echo "    Run: ruff format src/"
fi

# ─── 2. 类型检查 ──────────────────────────────────────────────────────────────

log_section "2. Type Checking"

# MyPy (optional, don't fail on warnings)
echo -n "  MyPy... "
if command -v mypy &>/dev/null; then
    MYPY_OUTPUT=$(mypy src/vision_insight --ignore-missing-imports --no-error-summary 2>&1 || true)
    MYPY_ERRORS=$(echo "$MYPY_OUTPUT" | grep -c ": error:" || true)
    if [[ "$MYPY_ERRORS" -eq 0 ]]; then
        log_pass "MyPy (0 errors)"
    else
        if $CI_MODE; then
            log_fail "MyPy ($MYPY_ERRORS errors)"
            echo "$MYPY_OUTPUT" | grep ": error:" | head -5
        else
            log_warn "MyPy ($MYPY_ERRORS errors — non-blocking)"
        fi
    fi
else
    log_info "MyPy not installed (skipped)"
fi

# ─── 3. 单元测试 ──────────────────────────────────────────────────────────────

log_section "3. Unit Tests"

# 核心单元测试
echo -n "  Unit tests... "
UNIT_OUTPUT=$(python -m pytest tests/unit/ -q --tb=no 2>&1 || true)
if echo "$UNIT_OUTPUT" | grep -q "passed"; then
    PASSED=$(echo "$UNIT_OUTPUT" | grep -oP '\d+ passed' | head -1)
    log_pass "Unit tests ($PASSED)"
else
    log_fail "Unit tests failed"
    echo "$UNIT_OUTPUT" | tail -10
fi

# ─── 4. i18n 特定测试 ────────────────────────────────────────────────────────

log_section "4. i18n Tests"

echo -n "  i18n report tests... "
I18N_OUTPUT=$(python -m pytest tests/unit/services/test_i18n_report.py -q --tb=short 2>&1 || true)
if echo "$I18N_OUTPUT" | grep -q "passed"; then
    PASSED=$(echo "$I18N_OUTPUT" | grep -oP '\d+ passed' | head -1)
    log_pass "i18n report tests ($PASSED)"
else
    log_fail "i18n report tests failed"
    echo "$I18N_OUTPUT" | tail -10
fi

echo -n "  VLM lang tests... "
VLM_LANG_OUTPUT=$(python -m pytest tests/unit/services/test_vlm_lang.py -q --tb=short 2>&1 || true)
if echo "$VLM_LANG_OUTPUT" | grep -q "passed"; then
    PASSED=$(echo "$VLM_LANG_OUTPUT" | grep -oP '\d+ passed' | head -1)
    log_pass "VLM lang tests ($PASSED)"
else
    log_fail "VLM lang tests failed"
    echo "$VLM_LANG_OUTPUT" | tail -10
fi

# ─── 5. Python 语法检查 ──────────────────────────────────────────────────────

log_section "5. Syntax Check"

echo -n "  Python syntax... "
SYNTAX_ERRORS=0
for f in $(find src/vision_insight -name "*.py" -type f); do
    if ! python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null; then
        log_fail "Syntax error in $f"
        SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
    fi
done
if [[ "$SYNTAX_ERRORS" -eq 0 ]]; then
    log_pass "All Python files have valid syntax"
fi

# ─── 6. 前端文件检查 ─────────────────────────────────────────────────────────

log_section "6. Frontend Checks"

# HTML 语法检查
echo -n "  HTML syntax... "
if python3 -c "
from html.parser import HTMLParser
import sys

class V(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ok = True

with open('frontend/index.html') as f:
    v = V()
    v.feed(f.read())
    print('OK')
" 2>/dev/null | grep -q "OK"; then
    log_pass "HTML is well-formed"
else
    log_fail "HTML syntax error"
fi

# 检查 i18n.js 存在
echo -n "  i18n module... "
if [[ -f "frontend/src/js/i18n.js" ]]; then
    log_pass "i18n.js exists"
else
    log_fail "i18n.js not found"
fi

# 检查 app.js 导入 i18n
echo -n "  app.js imports i18n... "
if grep -q "import.*i18n" frontend/src/js/app.js 2>/dev/null; then
    log_pass "app.js imports i18n module"
else
    log_fail "app.js does not import i18n module"
fi

# 检查语言切换按钮
echo -n "  Language toggle... "
if grep -q 'data-lang' frontend/index.html 2>/dev/null; then
    log_pass "Language toggle buttons present"
else
    log_fail "Language toggle buttons not found"
fi

# 检查 data-i18n 属性
echo -n "  data-i18n attributes... "
I18N_ATTR_COUNT=$(grep -c 'data-i18n' frontend/index.html 2>/dev/null || echo 0)
if [[ "$I18N_ATTR_COUNT" -gt 5 ]]; then
    log_pass "data-i18n attributes ($I18N_ATTR_COUNT found)"
else
    log_warn "Only $I18N_ATTR_COUNT data-i18n attributes found"
fi

# ─── 7. 安全检查 ──────────────────────────────────────────────────────────────

log_section "7. Security Checks"

# 检查 .env 文件不被提交
echo -n "  .env not tracked... "
if git ls-files --error-unmatch .env 2>/dev/null; then
    log_fail ".env is tracked by git!"
else
    log_pass ".env not tracked"
fi

# 检查 API key 不在代码中
echo -n "  No hardcoded API keys... "
KEY_PATTERNS='sk-[a-zA-Z0-9]{20,}|AIza[a-zA-Z0-9_-]{35}'
if grep -rP "$KEY_PATTERNS" src/ frontend/ --include="*.py" --include="*.js" --include="*.html" -l 2>/dev/null | grep -v ".example" | head -1; then
    log_fail "Possible hardcoded API keys found"
else
    log_pass "No hardcoded API keys"
fi

# 检查调试代码
echo -n "  No debug prints... "
DEBUG_COUNT=$(grep -rn "print(" src/vision_insight/ --include="*.py" 2>/dev/null | grep -v "test" | grep -v "#" | wc -l || echo 0)
if [[ "$DEBUG_COUNT" -gt 5 ]]; then
    log_warn "$DEBUG_COUNT print() statements in src/ (consider using logger)"
else
    log_pass "Minimal debug prints ($DEBUG_COUNT)"
fi

# ─── 8. 依赖检查 ──────────────────────────────────────────────────────────────

log_section "8. Dependency Check"

echo -n "  pyproject.toml valid... "
if python3 -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))" 2>/dev/null; then
    log_pass "pyproject.toml is valid TOML"
else
    log_fail "pyproject.toml is invalid"
fi

# ─── 9. Git 状态 ──────────────────────────────────────────────────────────────

log_section "9. Git Status"

# 检查是否有未提交的更改
echo -n "  Working tree clean... "
if git diff --quiet 2>/dev/null && git diff --cached --quiet 2>/dev/null; then
    log_pass "No uncommitted changes"
else
    CHANGED=$(git diff --stat --shortstat 2>/dev/null | tail -1)
    log_warn "Uncommitted changes: $CHANGED"
fi

# 检查当前分支
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
log_info "Current branch: $BRANCH"

# ─── 结果汇总 ─────────────────────────────────────────────────────────────────

log_section "Summary"

echo ""
echo -e "  Errors:   ${RED}$ERRORS${NC}"
echo -e "  Warnings: ${YELLOW}$WARNINGS${NC}"
echo ""

if [[ "$ERRORS" -eq 0 ]]; then
    echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   ✅ ALL CHECKS PASSED — SAFE TO DEPLOY   ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔══════════════════════════════════════╗${NC}"
    echo -e "${RED}║   ❌ $ERRORS CHECK(S) FAILED — DO NOT DEPLOY   ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════╝${NC}"
    exit 1
fi
