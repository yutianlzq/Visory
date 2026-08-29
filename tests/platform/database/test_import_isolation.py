from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_importing_platform_repository_does_not_load_legacy_storage() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import src.repositories.platform; "
                "assert 'src.storage' not in sys.modules; "
                "assert 'data_provider' not in sys.modules"
            ),
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
