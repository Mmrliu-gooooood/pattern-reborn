"""Write a redacted local health report; never send it or read secret values."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from importlib import metadata, util
import json
from pathlib import Path
import platform
import socket
import struct
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def report(root: Path) -> dict:
    required = {"pattern-reborn": "pattern_reborn", "fastapi": "fastapi", "uvicorn": "uvicorn",
                "Pillow": "PIL", "numpy": "numpy", "opencv-python-headless": "cv2", "pydantic": "pydantic"}
    dependencies = {}
    for package, module in required.items():
        try:
            dependencies[package] = {"version": metadata.version(package), "importable": util.find_spec(module) is not None}
        except (metadata.PackageNotFoundError, ImportError, ValueError):
            dependencies[package] = {"version": None, "importable": False}
    with socket.socket() as probe:
        probe.settimeout(0.3)
        occupied = probe.connect_ex(("127.0.0.1", 8510)) == 0
    projects, malformed = 0, 0
    for path in (root / "workspace").glob("*/project.json"):
        projects += 1
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("schema_version") != 1:
                malformed += 1
        except (OSError, ValueError, AttributeError):
            malformed += 1
    return {"format": "pattern-reborn-diagnostic-v1", "created_at": datetime.now(UTC).isoformat(),
            "python": platform.python_version(), "python_311_x64": sys.version_info[:2] == (3, 11) and struct.calcsize("P") == 8,
            "platform": platform.system(), "dependencies": dependencies,
            "frontend_built": (root / "web/dist/client/index.html").is_file(),
            "port_8510_in_use": occupied,
            "local_storage": {name: (root / name).is_dir() for name in ("workspace", "outputs", "models", "config")},
            "project_records": projects, "malformed_or_other_schema_records": malformed,
            "credential_files_present": {"dotenv": (root / ".env").is_file(), "streamlit_secrets": (root / ".streamlit/secrets.toml").is_file()},
            "privacy": "No secret values, file paths, project names, images or provider URLs included. Review before sharing."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or ROOT / ".cache/diagnostics" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6] + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(report(ROOT), stream, ensure_ascii=False, indent=2)
    print(destination)
