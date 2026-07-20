"""Dashboard smoke tests — the app runs clean and the Phase 4-6 tab builders
render straight from the committed docs/results JSONs (no recomputation)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "dashboard" / "app.py"
RESULTS = ROOT / "docs" / "results"

streamlit_missing = importlib.util.find_spec("streamlit") is None
pytestmark = pytest.mark.skipif(streamlit_missing, reason="needs pip install -e '.[ui]'")


@pytest.fixture(scope="module")
def app_module():
    """Load dashboard/app.py bare (st.* calls are harmless outside a run)."""
    spec = importlib.util.spec_from_file_location("dashboard_app_under_test", APP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_app_runs_without_exception():
    """Full script health check — every tab executes against committed JSONs."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    assert not at.exception


@pytest.mark.parametrize(
    ("filename", "builder"),
    [
        ("phase4_dml.json", "render_phase4"),
        ("phase5_hetero.json", "render_phase5"),
        ("phase6_realdata.json", "render_phase6"),
    ],
)
def test_tab_builders_run_on_committed_json(app_module, filename, builder):
    data = json.loads((RESULTS / filename).read_text())
    getattr(app_module, builder)(data)  # must not raise


def test_missing_results_file_degrades_to_none(app_module):
    """Empty state: a gitignored/absent JSON yields None, never an exception."""
    assert app_module.load_results_json(str(RESULTS / "does_not_exist.json")) is None
