from __future__ import annotations

import datetime as dt
import time

from .main import run_cycle


def sleep_until_next_hour() -> None:
    now = dt.datetime.now(dt.UTC)
    next_hour = (now + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    sleep_seconds = max(1, int((next_hour - now).total_seconds()))
    time.sleep(sleep_seconds)


def main() -> None:
    print("[scheduler] BURCH-EIDOLON scheduler started (hourly)")
    while True:
        run_cycle()
        sleep_until_next_hour()


if __name__ == "__main__":
    main()
