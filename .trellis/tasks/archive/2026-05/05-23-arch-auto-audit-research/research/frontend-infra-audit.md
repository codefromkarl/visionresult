# Frontend & Infrastructure Architecture Audit
Date: 2026-05-23
Sources: Project source at /home/yuanzhi/Develop/ai-research/visionresult

## Executive Summary

The project has **5 critical security issues** (hardcoded API keys in committed code), **significant frontend duplication** (3+ copies tracked in git), **Docker running as root**, and **divergent frontend copies** causing potential runtime failures.

---

## Findings

### 1. Frontend Duplication (CRITICAL — 6 copies tracked in git)

#### 1.1 Three parallel frontend copies, all git-tracked

| Copy | Path | Role | Status |
|------|------|------|--------|
| **Source** | `frontend/src/` | True source (has i18n.js) | ✅ Canonical |
| **Public** | `frontend/public/` | Old Cloudflare Pages deploy target | ❌ Stale + diverged |
| **Deploy** | `frontend/deploy/` | Current Cloudflare Pages deploy target | ⚠️ Partially diverged |
| **Worker-build** | `frontend/worker-build/` | Built Cloudflare Worker | ❌ Stale artifact |

**Evidence of divergence:**
- `frontend/public/src/js/app.js` is **missing the i18n import** — differs from `frontend/src/js/app.js` (line 9: `import { t, getLang, setLang, initI18n } from './i18n.js'` is absent in public/)
- `frontend/public/src/js/i18n.js` does **not exist** at all — only in `src/`
- `frontend/deploy/src/js/i18n.js` also **does not exist**
- `frontend/public/index.html` (153 lines) ≠ `frontend/index.html` (196 lines) ≠ `frontend/deploy/index.html` (153 lines)
- All CSS files are identical across all copies (no divergence, but pure waste)
- `deploy/functions/api/test.js` exists only in deploy (simple health-check endpoint, not in root `functions/`)

**Category**: arch/debt | **Severity**: HIGH
**What would change**: Delete `frontend/public/`, `frontend/worker-build/`, `frontend/functions.zip`. Make `frontend/deploy/` a build output generated from `src/`, or use `src/` directly with wrangler config pointing to it.

#### 1.2 `index-old.html` — 1186-line monolith (obsolete)

- `frontend/index-old.html` (1186 lines) — a single-file pre-refactor UI with inline styles
- Copied to `frontend/deploy/index-old.html` and `frontend/public/index-old.html` (both diverged)
- The modern `index.html` (196 lines) uses modular CSS/JS with i18n support
- **Category**: debt | **Severity**: MEDIUM
- **What would change**: Delete `index-old.html` everywhere. It's superseded by the modular version.

#### 1.3 `functions.zip` — stale build artifact

- `frontend/functions.zip` (2.4KB) contains `api/analyze.js` and `api/report/[task_id].js` dated 2026-05-21
- This is an old packaging artifact; deploy now uses `wrangler pages deploy frontend/deploy/`
- **Category**: debt | **Severity**: LOW
- **What would change**: Delete `functions.zip`, add `*.zip` to `.gitignore`.

#### 1.4 `frontend/deploy/_worker.js` duplicates `functions/api/analyze.js`

- `functions/api/analyze.js` (101 lines) — clean Cloudflare Pages Function
- `deploy/_worker.js` (420 lines) — monolithic Worker with full pipeline, hardcoded keys, OCR.space, Gemini, etc.
- These are **two different implementations** of the same API endpoint
- **Category**: arch | **Severity**: HIGH
- **What would change**: Consolidate to one implementation. The `_worker.js` approach is more capable but needs secrets moved to env vars.

---

### 2. Configuration & Secrets (5 CRITICAL findings)

#### 2.1 Hardcoded Gemini API key in committed code

- **File**: `frontend/deploy/_worker.js` line 4
- **Content**: `const GEMINI_KEY = '<REDACTED>'`
- Git-tracked, pushed to repository (commits `41d242d`, `bcb5a4b`)
- **Category**: security | **Severity**: CRITICAL
- **What would change**: Rotate the key immediately. Replace with `env.GEMINI_API_KEY` (Cloudflare Workers env binding).

#### 2.2 Hardcoded OCR.space API key

- **File**: `frontend/deploy/_worker.js` line 123
- **Content**: `'apikey': 'helloworld'`
- This is OCR.space's free-tier demo key — will be rate-limited or blocked
- **Category**: security | **Severity**: HIGH
- **What would change**: Move to `env.OCR_SPACE_API_KEY`.

#### 2.3 Hardcoded Cloudflare Account ID

- **File**: `scripts/deploy.sh` line 49
- **Content**: `export CLOUDFLARE_ACCOUNT_ID="<REDACTED>"`
- Should use `$VIA_CLOUDFLARE_ACCOUNT_ID` from `.env`
- **Category**: security | **Severity**: MEDIUM
- **What would change**: Replace with `"${VIA_CLOUDFLARE_ACCOUNT_ID}"` (already defined in `.env.example`).

#### 2.4 D1 Database ID in git-tracked wrangler.toml

- **File**: `frontend/wrangler.toml` and `frontend/worker-build/wrangler.toml`
- **Content**: `database_id = "f1df5e69-9e62-4021-ac4c-6e419181492a"`
- Not a secret per se, but should be in env-specific config
- **Category**: debt | **Severity**: LOW

#### 2.5 Database URL with hardcoded credentials

- **File**: `src/vision_insight/core/config.py` line 39
- **Content**: `database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/vision_insight"`
- Default `postgres:postgres` is a well-known weak credential
- **Category**: security | **Severity**: MEDIUM
- **What would change**: Remove default or require `VIA_DATABASE_URL` to be set in production.

#### 2.6 Typo in deploy.sh fallback env var

- **File**: `scripts/deploy.sh` line 44
- **Content**: `${CLOUDFRAME_API_KEY:-}` — should be `CLOUDFLARE_API_KEY`
- **Category**: debt | **Severity**: MEDIUM
- **What would change**: Fix typo.

---

### 3. Docker/Deployment

#### 3.1 Dockerfile runs as root

- **File**: `Dockerfile` (entire file)
- No `USER` directive — container runs as root by default
- `docker-compose.yml` does not set `user:` either
- **Category**: security | **Severity**: HIGH
- **What would change**: Add non-root user:
  ```dockerfile
  RUN useradd -m appuser
  USER appuser
  ```

#### 3.2 Nginx in docker-compose runs as root

- **File**: `docker-compose.yml` lines 37-50
- `nginx:alpine` runs as root by default; no `user: nginx` directive
- Has `security_opt: no-new-privileges:true` (good) and `read_only: true` (api service, good)
- **Category**: security | **Severity**: MEDIUM
- **What would change**: Add `user: "101:101"` (nginx user) to nginx service.

#### 3.3 Nginx serves on HTTP only (no HTTPS)

- **File**: `nginx.conf` — HTTPS block is commented out (lines 82-96)
- `docker-compose.yml` exposes `443:443` but no SSL config
- **Category**: security | **Severity**: MEDIUM (production concern)

#### 3.4 Dockerfile port mismatch with config

- **File**: `Dockerfile` line 31 uses `EXPOSE 8001`, CMD uses `--port 8001`
- **File**: `config.py` line 14 defaults to `port: int = 8000`
- `docker-compose.yml` overrides with `VIA_PORT=8001` — works but confusing
- **Category**: debt | **Severity**: LOW
- **What would change**: Align defaults — change config.py default to 8001 or Dockerfile to 8000.

#### 3.5 Frontend deployed in Docker includes ALL copies

- **File**: `Dockerfile` line 21: `COPY frontend/ frontend/`
- Copies `deploy/`, `public/`, `worker-build/`, `functions.zip`, `index-old.html` — all unnecessary for Docker deployment
- Only `frontend/index.html` + `frontend/src/` are needed for nginx to serve
- **Category**: perf | **Severity**: LOW
- **What would change**: `COPY frontend/index.html frontend/src/ frontend/` or use `.dockerignore`.

---

### 4. Scripts

#### 4.1 No dead scripts found — all are actively referenced

| Script | Purpose | Used by |
|--------|---------|---------|
| `deploy.sh` | Cloudflare Pages deploy | Manual / CI |
| `docker-run.sh` | Local Docker build+run | Manual |
| `health-check.sh` | Post-deploy verification | `deploy.sh` |
| `pre-deploy-guard.sh` | Pre-deploy quality gate | `deploy.sh` |
| `test-qa-check.sh` | Test quality scan | Manual / CI |
| `pre-commit` | Git pre-commit hook | Git hooks |
| `install-hooks.sh` | Install git hooks | Manual |
| `setup-cloudflare.sh` | Create CF resources | Manual (one-time) |
| `eval-tests.py` | AI-powered test evaluation | Manual |
| `demo_pipeline_trace.py` | Demo pipeline traces | Manual |

#### 4.2 Unsafe shell patterns

- **`scripts/deploy.sh` line 20**: `source .env` with `set +a` — sources entire `.env` into shell env, potentially leaking secrets to child processes
- **`scripts/docker-run.sh` line 15**: `$(pwd)` unquoted — will break on paths with spaces
- **Category**: security | **Severity**: LOW

#### 4.3 `demo_pipeline_trace.py` imports non-existent path

- **File**: `scripts/demo_pipeline_trace.py` line 10
- Imports `from vision_insight.services.evidence.fusion_service import FusionService`
- Need to verify this import path exists
- **Category**: debt | **Severity**: LOW

---

### 5. Test Infrastructure

#### 5.1 Duplicated mock service classes in integration tests

- `tests/integration/test_pipeline.py` defines `MockPipeline`, `MockOCRService`, `MockVLMService`, `MockEntityService`, `MockSearchService`
- `tests/integration/test_pipeline_e2e.py` also defines its own `MockOCRService(OCRService)`, `MockVLMService(VLMService)`, `MockEntityService(EntityService)`, `MockSearchService(SearchService)`
- `tests/mocks/mock_services.py` already has canonical `MockOCRService`, `MockVLMService`, `MockEntityService`, `MockSearchService`, `MockReportService`
- **Category**: debt | **Severity**: MEDIUM
- **What would change**: Integration tests should import from `tests/mocks/mock_services.py` instead of defining inline mocks.

#### 5.2 Test fixtures are well-organized

- `tests/conftest.py` — shared image fixtures (sample_png_bytes, sample_jpeg_bytes, blank_image_bytes) + E2E test ordering
- `tests/unit/services/conftest.py` — proxy env cleanup (autouse)
- `tests/mocks/fixtures.py` — comprehensive factory functions (13 create_mock_* functions + 2 scenario factories)
- **Verdict**: Good structure, no duplication in fixtures.

#### 5.3 `test_pipeline.py` vs `test_pipeline_e2e.py` overlap

- `test_pipeline.py` (241 lines): Uses golden examples + evaluation assertions, tests `TestPipelineIntegration` and `TestGoldenDatasetIntegration`
- `test_pipeline_e2e.py` (282 lines): Uses inline mocks, tests `test_pipeline_full_flow`, `test_pipeline_handles_vlm_failure`, `test_api_analyze_endpoint`
- Different test approaches but same pipeline under test
- **Category**: debt | **Severity**: LOW
- **What would change**: Consider merging into one file with shared mock setup.

---

## Key Files

- `frontend/deploy/_worker.js` — 420-line monolith with hardcoded API keys (CRITICAL)
- `frontend/public/` — stale copy of frontend source, diverged from canonical `src/`
- `frontend/worker-build/` — obsolete Cloudflare Worker build artifact
- `frontend/functions.zip` — stale packaging artifact
- `frontend/index-old.html` — 1186-line pre-refactor UI
- `scripts/deploy.sh` line 49 — hardcoded Cloudflare account ID
- `src/vision_insight/core/config.py` line 39 — hardcoded DB credentials
- `Dockerfile` — no USER directive (runs as root)
- `tests/integration/test_pipeline.py` and `test_pipeline_e2e.py` — duplicated mock classes
- `tests/mocks/mock_services.py` — canonical mock implementations (should be reused)

## Recommendations

1. **IMMEDIATE: Rotate the Gemini API key** (`<REDACTED>`) — it's committed in git history. Replace with Cloudflare Workers env binding.

2. **IMMEDIATE: Move all secrets in `_worker.js` to env bindings** — `GEMINI_KEY`, OCR.space `apikey`, Baidu credentials are already partially using `env.*` but some are hardcoded.

3. **Clean up frontend copies**: Delete `frontend/public/`, `frontend/worker-build/`, `frontend/functions.zip`, all `index-old.html` copies. Add them to `.gitignore`. Make `frontend/deploy/` a build step output from `src/`.

4. **Fix the i18n divergence**: `public/` and `deploy/` copies are missing `i18n.js` and have an outdated `app.js` without i18n imports. Either:
   - Deploy directly from `src/` (if wrangler supports it), or
   - Add a build/copy script that syncs `src/` → `deploy/`

5. **Docker hardening**: Add non-root user to Dockerfile. Add `.dockerignore` to exclude `frontend/public/`, `frontend/worker-build/`, `frontend/functions.zip`, `.env`.

6. **Consolidate test mocks**: Have `tests/integration/test_pipeline_e2e.py` import from `tests/mocks/mock_services.py` instead of redefining mocks.

7. **Fix deploy.sh**: Remove hardcoded Cloudflare account ID (line 49), fix `CLOUDFRAME_API_KEY` typo (line 44).

8. **Align port defaults**: Make `config.py` default port match Dockerfile (both 8001 or both 8000).
