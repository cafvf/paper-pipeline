import subprocess
import sys
import pytest


@pytest.mark.integration
def test_cli_module_entrypoint_is_available():
    result = subprocess.run(
        [sys.executable, "-m", "paper_pipeline.cli", "run", "--vault-root", ".", "--dry-run"],
        cwd=".",
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "dry-run" in result.stdout
