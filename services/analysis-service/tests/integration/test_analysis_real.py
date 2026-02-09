import os
import subprocess
import sys
from pathlib import Path


def test_analysis_mock():
    script_path = Path(__file__).with_name("run_analysis_real.py")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        check=False,
        env=os.environ.copy(),
    )
    assert result.returncode == 0
