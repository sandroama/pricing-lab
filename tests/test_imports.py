"""Cheap import smoke tests."""


def test_pricelab_imports():
    import pricelab  # noqa: F401
    from pricelab.simulation import MarketplaceSimulator, MarketplaceConfig  # noqa: F401
    from pricelab.estimators import naive_ab_ate, switchback_ate  # noqa: F401
    from pricelab.evaluation import (  # noqa: F401
        run_phase1_naive_ab,
        run_phase2_switchback_vs_naive,
    )


def test_api_module_loads():
    from pricelab.api.main import app

    assert app is not None
    routes = {r.path for r in app.routes}
    expected = {
        "/health",
        "/v1/simulate",
        "/v1/estimate/naive",
        "/v1/estimate/switchback",
        "/v1/compare",
    }
    assert expected.issubset(routes)
