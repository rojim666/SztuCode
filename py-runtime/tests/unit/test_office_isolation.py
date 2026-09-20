"""The frozen office helper must not initialize the agent or prompt catalog."""
import subprocess
import sys


def test_office_import_does_not_load_agent_modules() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "\n".join([
            "import sys",
            "from sztu_code.core.office import execute_office_request",
            "assert 'sztu_code.core.tools' not in sys.modules",
            "assert 'sztu_code.core.prompts' not in sys.modules",
            "assert 'sztu_code.core.runner' not in sys.modules",
        ])],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
