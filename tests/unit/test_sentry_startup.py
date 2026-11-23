from __future__ import annotations

import os
import subprocess
import sys


def test_backend_import_with_sentry_enabled():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import main; import sentry_sdk; assert sentry_sdk.get_client().is_active()",
        ],
        env={
            **os.environ,
            "SENTRY_DSN": "http://test@127.0.0.1:1/1",
            "SENTRY_TRACES_SAMPLE_RATE": "0",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
