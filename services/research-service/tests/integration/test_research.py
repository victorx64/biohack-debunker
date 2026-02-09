import os
import subprocess
import sys
from pathlib import Path


def test_research():
    script_path = Path(__file__).with_name("run_research.py")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        check=False,
        env=os.environ.copy(),
    )
    assert result.returncode == 0
