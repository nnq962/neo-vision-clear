"""Cho phép chạy package bằng ``python -m walkway_monitor``."""

from walkway_monitor.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
