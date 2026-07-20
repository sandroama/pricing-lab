# pricing-lab — common dev tasks. `make help` for the menu.

.PHONY: help install install-dev test smoke api ui phase1 phase2 phase2-adjusted phase2-ri phase3 phase3b phase4 phase5 phase6 clean format lint typecheck

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime deps only
	pip install -e .

install-dev:  ## Install dev + ui extras
	pip install -e ".[dev,ui]"

test:  ## Run pytest
	pytest tests/ -v

smoke:  ## End-to-end smoke (Phase 1 + Phase 2 with assertion)
	python scripts/run_pricing_smoke.py

phase1:  ## Phase 1 — naive A/B sweep over spillover
	python scripts/run_phase1_naive_ab.py

phase2:  ## Phase 2 — switchback vs naive head-to-head
	python scripts/run_phase2_switchback_compare.py

phase2-adjusted:  ## Phase 2b — regression-adjusted switchback precision audit
	python scripts/run_phase2_regression_adjusted.py

phase2-ri:  ## Phase 2c — randomization-inference audit of clustered CIs (~10 min)
	python scripts/run_phase2c_randomization_inference.py

phase3:  ## Phase 3 — switchback block-size sensitivity sweep
	python scripts/run_phase3_block_size.py

phase3b:  ## Phase 3b — sub-day switchback stratification vs aliasing spike
	python scripts/run_phase3b_stratified_switchback.py

phase4:  ## Phase 4 — naive OLS vs Double ML elasticity (needs [causal] extra)
	python scripts/run_phase4_dml.py

phase5:  ## Phase 5 — heterogeneous elasticity + revenue optimizer (needs [causal] extra)
	python scripts/run_phase5_hetero.py

phase6:  ## Phase 6 — Citi Bike real-data walk-forward (download cmd in script header)
	python scripts/run_phase6_realdata.py

api:  ## Run FastAPI dev server (http://localhost:8000/docs)
	uvicorn pricelab.api.main:app --reload

ui:  ## Run Streamlit dashboard (http://localhost:8501)
	streamlit run dashboard/app.py

format:  ## Auto-format with ruff
	ruff format src tests scripts dashboard

lint:  ## Lint with ruff
	ruff check src tests scripts dashboard

typecheck:  ## Run mypy
	mypy src

clean:  ## Remove build / test caches
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache **/__pycache__
