from __future__ import annotations

import json
import os
import subprocess
import tempfile
from glob import glob
from typing import Dict, Protocol

from .errors import TranscriptFetchError


class YtDlpRunner(Protocol):
    def extract_info(self, url: str) -> Dict:
        ...

    def download_caption(self, url: str, language: str, is_auto: bool, ext: str) -> str:
        ...


class ProcessYtDlpRunner:
    def __init__(self, binary: str = "yt-dlp") -> None:
        self._binary = binary

    def extract_info(self, url: str) -> Dict:
        result = self._run(["-J", "--skip-download", url])
        try:
            return json.loads(result)
        except json.JSONDecodeError as exc:
            raise TranscriptFetchError("yt-dlp returned invalid JSON") from exc

    def download_caption(self, url: str, language: str, is_auto: bool, ext: str) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, "%(id)s.%(ext)s")
            args = [
                "--skip-download",
                "--sub-lang",
                language,
                "--sub-format",
                ext,
                "-o",
                output_template,
            ]
            if is_auto:
                args.append("--write-auto-sub")
            else:
                args.append("--write-sub")
            args.append(url)
            self._run(args)

            pattern = os.path.join(tmpdir, f"*.{language}.{ext}")
            matches = sorted(glob(pattern))
            if not matches:
                fallback = sorted(glob(os.path.join(tmpdir, f"*.{language}.*")))
                matches = fallback
            if not matches:
                raise TranscriptFetchError("yt-dlp did not download subtitle file")

            subtitle_path = matches[-1]
            with open(subtitle_path, "r", encoding="utf-8") as handle:
                return handle.read()

    def _run(self, args: list[str]) -> str:
        command = [self._binary, *args]
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise TranscriptFetchError("yt-dlp binary not found") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            message = stderr or "yt-dlp command failed"
            raise TranscriptFetchError(message) from exc
        return completed.stdout
