#!/bin/bash
# Pre-commit 测试质量快速扫描
#
# 检查 3 项反模式：
# 1. E2E 测试是否只有结构检查
# 2. 测试文件是否有业务断言
# 3. 新增 service 是否有测试覆盖
#
# Usage: bash scripts/test-qa-check.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

echo "=== 测试质量快速扫描 ==="
echo ""

# ─── 1. E2E 测试行为检查 ──────────────────────────────────

echo -n "1. E2E 行为测试检查... "
E2E_DIR="tests/e2e"
if [[ -d "$E2E_DIR" ]]; then
  for f in "$E2E_DIR"/test_*.py; do
    [[ -f "$f" ]] || continue

    # 检查是否有用户操作模拟
    HAS_ACTION=$(grep -cE "set_input_files|click\(|fill\(|select_option|dispatch_event" "$f" || true)
    # 检查是否有行为断言
    HAS_BEHAVIOR=$(grep -cE "to_contain_class|to_contain_text|requests|wait_for_request" "$f" || true)
    # 检查是否只有结构检查
    ONLY_STRUCTURE=$(grep -cE "to_be_attached|to_be_visible" "$f" || true)

    if [[ "$HAS_ACTION" -eq 0 ]]; then
      echo -e "${RED}FAIL${NC}"
      echo "   ❌ $(basename "$f"): 缺少用户操作模拟 (set_input_files/click/fill)"
      ERRORS=$((ERRORS + 1))
    elif [[ "$HAS_BEHAVIOR" -eq 0 ]]; then
      echo -e "${RED}FAIL${NC}"
      echo "   ❌ $(basename "$f"): 缺少行为断言"
      ERRORS=$((ERRORS + 1))
    fi
  done
  echo -e "${GREEN}OK${NC}"
else
  echo -e "${YELLOW}SKIP${NC} (无 E2E 目录)"
fi

# ─── 2. 测试业务断言检查 ──────────────────────────────────

echo -n "2. 业务断言检查... "
WEAK_ASSERTS=0
for f in tests/unit/test_*.py tests/unit/services/test_*.py; do
  [[ -f "$f" ]] || continue

  # 检查是否有弱断言（只有 None 检查）
  STRONG_ASSERTS=$(grep -cE "assert.*[=!]= |assert.*>=|assert.*<=|assert.*in |assert.*not in " "$f" || true)

  if [[ "$STRONG_ASSERTS" -eq 0 ]]; then
    echo -e "${YELLOW}WARN${NC}"
    echo "   ⚠️  $(basename "$f"): 无强业务断言，只有弱断言"
    WEAK_ASSERTS=$((WEAK_ASSERTS + 1))
  fi
done
if [[ "$WEAK_ASSERTS" -eq 0 ]]; then
  echo -e "${GREEN}OK${NC}"
fi

# ─── 3. 新增 service 测试覆盖 ─────────────────────────────

echo -n "3. Service 测试覆盖检查... "
MISSING_TESTS=0
for f in src/vision_insight/services/*.py src/vision_insight/services/**/*.py; do
  [[ -f "$f" ]] || continue
  [[ "$(basename "$f")" == "__init__.py" ]] && continue

  # 查找对应测试
  STEM=$(basename "$f" .py)
  HAS_TEST=$(find tests -name "test_*.py" | xargs grep -l "$STEM" 2>/dev/null | head -1 || true)

  if [[ -z "$HAS_TEST" ]]; then
    echo -e "${YELLOW}WARN${NC}"
    echo "   ⚠️  $(basename "$f"): 无对应测试文件"
    MISSING_TESTS=$((MISSING_TESTS + 1))
  fi
done
if [[ "$MISSING_TESTS" -eq 0 ]]; then
  echo -e "${GREEN}OK${NC}"
fi

# ─── 结果 ──────────────────────────────────────────────────

echo ""
if [[ "$ERRORS" -eq 0 ]]; then
  echo -e "${GREEN}✅ 质量检查通过${NC}"
  exit 0
else
  echo -e "${RED}❌ $ERRORS 项检查失败${NC}"
  exit 1
fi
