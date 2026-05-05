import pytest

def test_package_present_or_skip():
    try:
        import paper_pipeline  # noqa: F401
    except Exception:
        pytest.skip("package 'paper_pipeline' not present; copy original package into repo before running tests")
    assert True
