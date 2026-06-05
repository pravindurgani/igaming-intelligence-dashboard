.PHONY: help setup install lint type test e2e clean clean-outputs all

help:  ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup:  ## Create venv and install dependencies
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -r requirements.txt
	@echo "✅ Setup complete. Run 'source .venv/bin/activate'"

install:  ## Install from lock file (deterministic)
	./.venv/bin/pip install -r requirements.lock
	@echo "✅ Installed from lock file"

lint:  ## Run code linters (ruff)
	./.venv/bin/ruff check scripts/ app/ tests/ src/ --select F,E,W,I,N,UP
	@echo "✅ Lint passed"

lint-fix:  ## Auto-fix linting issues
	./.venv/bin/ruff check scripts/ app/ tests/ src/ --select F,E,W,I,N,UP --fix
	@echo "✅ Auto-fixes applied"

type:  ## Run type checker (mypy)
	./.venv/bin/mypy scripts/main.py scripts/analysis.py --ignore-missing-imports
	@echo "✅ Type check passed"

test:  ## Run unit tests
	./.venv/bin/pytest tests/ -v --ignore=tests/e2e_idempotency.py
	@echo "✅ Unit tests passed"

e2e:  ## Run end-to-end idempotency tests
	./.venv/bin/pytest tests/e2e_idempotency.py -v --tb=short
	@echo "✅ E2E tests passed"

test-all:  ## Run all tests (unit + e2e)
	./.venv/bin/pytest tests/ -v --tb=short
	@echo "✅ All tests passed"

clean:  ## Remove generated files and caches
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf app/__pycache__ scripts/__pycache__ tests/__pycache__ src/__pycache__
	rm -f data/*.tmp
	@echo "✅ Cleaned caches"

clean-outputs:  ## Remove timestamped output files (keep *_latest.csv)
	./.venv/bin/python scripts/cleanup_old_outputs.py
	@echo "✅ Cleaned output files"

verify:  ## Run verification checks (atomic writes, dedup, etc.)
	bash verify_fixes.sh
	@echo "✅ Verification complete"

pipeline:  ## Run full pipeline
	./.venv/bin/python run_pipeline.py
	@echo "✅ Pipeline complete"

pipeline-headless:  ## Run pipeline headless (no dashboard)
	./.venv/bin/python run_pipeline.py --no-dashboard --headless
	@echo "✅ Pipeline complete (headless)"

dashboard:  ## Start Streamlit dashboard
	./.venv/bin/streamlit run app/dashboard.py

scheduler:  ## Start background scheduler (runs daily at 8am GMT)
	./.venv/bin/python scheduler.py
	@echo "✅ Scheduler started"

scheduler-once:  ## Run pipeline once immediately
	./.venv/bin/python scheduler.py --once
	@echo "✅ Pipeline executed"

all: lint type test e2e  ## Run all quality checks

# CI/CD targets
ci: lint type test  ## Run CI checks (no e2e)
	@echo "✅ CI checks passed"

pre-commit:  ## Install pre-commit hooks
	./.venv/bin/pip install pre-commit
	./.venv/bin/pre-commit install
	@echo "✅ Pre-commit hooks installed"

freeze:  ## Update requirements.lock
	./.venv/bin/pip freeze > requirements.lock
	@echo "✅ Updated requirements.lock"
