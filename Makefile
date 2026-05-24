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
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

format: ## 自动格式化
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

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

# ─── 生产环境部署 ──────────────────────────────────────────
.PHONY: prod-up prod-down prod-logs prod-status prod-backup

prod-up: ## 启动生产环境
	docker compose -f docker-compose.prod.yml up -d
	@echo "✅ 生产环境已启动"
	@echo "   API: https://imagerecognition.codefromkarl.xyz"
	@echo "   健康检查: https://imagerecognition.codefromkarl.xyz/health"

prod-down: ## 停止生产环境
	docker compose -f docker-compose.prod.yml down

prod-logs: ## 查看生产环境日志
	docker compose -f docker-compose.prod.yml logs -f

prod-status: ## 查看生产环境状态
	docker compose -f docker-compose.prod.yml ps
	@echo ""
	@echo "📊 健康检查:"
	@curl -s https://imagerecognition.codefromkarl.xyz/health/detailed 2>/dev/null | python3 -m json.tool || echo "⚠️ 无法访问生产环境"

prod-backup: ## 备份生产数据库
	@echo "📦 备份 PostgreSQL 数据库..."
	@mkdir -p backups
	docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres vision_insight > backups/vision_insight_$$(date +%Y%m%d_%H%M%S).sql
	@echo "✅ 备份完成: backups/"

prod-restore: ## 恢复数据库（用法: make prod-backup FILE=backup.sql）
	@if [ -z "$(FILE)" ]; then echo "❌ 请指定备份文件: make prod-restore FILE=backups/xxx.sql"; exit 1; fi
	@echo "📥 恢复数据库: $(FILE)"
	docker compose -f docker-compose.prod.yml exec -T db psql -U postgres vision_insight < $(FILE)
	@echo "✅ 恢复完成"

prod-ssl: ## 初始化 SSL 证书
	chmod +x scripts/init-ssl.sh
	./scripts/init-ssl.sh imagerecognition.codefromkarl.xyz

prod-migrate: ## 迁移 SQLite 到 PostgreSQL
	@if [ -z "$(PG_URL)" ]; then echo "❌ 请指定 PostgreSQL URL: make prod-migrate PG_URL=postgresql+asyncpg://user:pass@host/db"; exit 1; fi
	python scripts/migrate-to-postgres.py --sqlite-path data/vision_insight.db --pg-url "$(PG_URL)"

# ─── 性能测试 ──────────────────────────────────────────────
.PHONY: benchmark benchmark-local benchmark-prod

benchmark: ## 运行性能测试（默认本地）
	@echo "🚀 Running benchmark..."
	python scripts/benchmark.py --host http://localhost:8000 --requests 50 --concurrent 5

benchmark-local: ## 本地性能测试
	@echo "🚀 Running local benchmark..."
	python scripts/benchmark.py --host http://localhost:8000 --requests 100 --concurrent 10

benchmark-prod: ## 生产环境性能测试
	@echo "🚀 Running production benchmark..."
	python scripts/benchmark.py --host https://imagerecognition.codefromkarl.xyz --requests 50 --concurrent 5
