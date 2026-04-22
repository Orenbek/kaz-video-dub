from __future__ import annotations

import json
import subprocess
from pathlib import Path


class FFProbeError(RuntimeError):
    pass


def probe_duration(path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FFProbeError(result.stderr.strip() or f"ffprobe failed for {path}")
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])
