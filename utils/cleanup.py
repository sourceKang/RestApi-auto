from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress


class CleanupRegistry:
    def __init__(self) -> None:
        self._callbacks: list[Callable[[], None]] = []

    def add(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def run(self) -> None:
        while self._callbacks:
            callback = self._callbacks.pop()
            with suppress(Exception):
                callback()

