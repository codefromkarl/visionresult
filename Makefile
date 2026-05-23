# ─── Vision Insight Agent — 开发命令 ─────────────────────
# 用法: make <target>

.PHONY: lint format test check mypy quality dev-setup

# 快捷入口
dev-setup: ## 初始化开发环境
	uv sync --extra dev
	uv run pre-commit install
	@echo "✅ 开发环境就绪"

# ─── 质量检查 ─────────────────────────────────────────────
lint: ## Ruff 检查
	uv run ruff check .
	uv run ruff format --check .

format: ## 自动格式化
	uv run ruff check --fix .
	uv run ruff format .

mypy: ## 类型检查
	uv run mypy src/vision_insight

test: ## 运行全部测试
	uv run pytest tests/ -q

test-unit: ## 仅单元测试
	uv run pytest tests/unit/ -q

test-cov: ## 测试 + 覆盖率报告
	uv run pytest tests/ \
		--cov=vision_insight \
		--cov-report=term-missing \
		--cov-fail-under=60 \
		-q

# ─── 质量门禁（等同 CI）─────────────────────────────────────
quality: lint mypy test ## 完整质量门禁：lint + 类型 + 测试
	@echo "✅ 所有质量检查通过"

# ─── 类型治理追踪 ──────────────────────────────────────────
type-audit: ## 审计 type: ignore 数量
	@echo "📊 type: ignore 统计:"
	@grep -r "# type: ignore" src/vision_insight/ --include="*.py" | wc -l | xargs -I{} echo "   总数: {}"
	@grep -r "# type: ignore" src/vision_insight/ --include="*.py" -l | sort | while read f; do \
		count=$$(grep -c "# type: ignore" "$$f"); \
		echo "   $$f: $$count"; \
	done

type-report: ## mypy 详细报告
	uv run mypy src/vision_insight --no-error-summary 2>&1 | grep "error:" || echo "✅ 零错误"
