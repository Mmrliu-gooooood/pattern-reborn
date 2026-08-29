# -*- coding: utf-8 -*-
"""Launch a bound Streamlit child for smoke tests and always stop that child."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
_HEALTH_WAIT_SECONDS = 15.0
_TERMINATE_WAIT_SECONDS = 5.0


@contextmanager
def streamlit_server(
    app: Path,
    port: int,
    env: Mapping[str, str] | None = None,
) -> Iterator[subprocess.Popen[bytes]]:
    app_path = Path(app)
    if not app_path.is_absolute():
        app_path = REPO_ROOT / app_path
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=true",
        f"--server.port={port}",
        "--server.address=127.0.0.1",
    ]
    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        env=dict(env) if env is not None else None,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_healthy(port, process)
        yield process
    finally:
        _stop_child(process)


def _wait_until_healthy(port: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + _HEALTH_WAIT_SECONDS
    last_error: Exception | None = None
    health_url = f"http://127.0.0.1:{port}/_stcore/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Streamlit exited before becoming healthy (code {process.returncode})."
            )
        try:
            with urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, OSError) as error:
            last_error = error
        time.sleep(0.25)
    raise TimeoutError(f"Streamlit health check at {health_url} failed: {last_error}")


def _stop_child(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=_TERMINATE_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=_TERMINATE_WAIT_SECONDS)
