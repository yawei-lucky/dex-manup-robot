#!/usr/bin/env python3
"""Tiny timeout watchdog simulation utility."""

from __future__ import annotations

import time


def did_timeout(start_ms: int, now_ms: int, timeout_ms: int) -> bool:
    return (now_ms - start_ms) > timeout_ms


def demo() -> int:
    start_ms = int(time.time() * 1000)
    time.sleep(0.03)
    now_ms = int(time.time() * 1000)
    print("timeout?", did_timeout(start_ms, now_ms, timeout_ms=10))
    return 0


if __name__ == "__main__":
    raise SystemExit(demo())
