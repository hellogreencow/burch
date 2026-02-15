from __future__ import annotations

import json
import time
from pathlib import Path

from .config import get_settings
from .tasks import discover_candidates, refresh_snapshot


def run_cycle() -> None:
    settings = get_settings()

    ok, status = refresh_snapshot(settings)
    print(f"[worker] refresh status={ok} message={status}")

    discoveries = discover_candidates(settings)
    out_dir = Path("/tmp/eidolon_discovery")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "latest.json"
    out_file.write_text(json.dumps(discoveries, indent=2), encoding="utf-8")
    print(f"[worker] discovery_count={len(discoveries)} file={out_file}")


def main() -> None:
    settings = get_settings()
    print("[worker] BURCH-EIDOLON worker started")
    while True:
        run_cycle()
        time.sleep(settings.worker_interval_seconds)


if __name__ == "__main__":
    main()
