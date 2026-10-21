from __future__ import annotations

from collections.abc import Callable


class StrictCleanupError(AssertionError):
    """A strict final cleanup failed after the test body (the device baseline was not restored).

    The pytest reporting hooks record a passed case whose strict cleanup fails as Blocked.
    """


class CleanupRegistry:
    def __init__(self) -> None:
        self._callbacks: list[tuple[Callable[[], None], bool]] = []

    def add(self, callback: Callable[[], None]) -> None:
        self._callbacks.append((callback, False))

    def add_final(self, callback: Callable[[], None]) -> None:
        self._callbacks.insert(0, (callback, False))

    def add_strict_final(self, callback: Callable[[], None]) -> None:
        self._callbacks.insert(0, (callback, True))

    def run(self) -> None:
        strict_errors: list[Exception] = []
        while self._callbacks:
            callback, strict = self._callbacks.pop()
            try:
                callback()
            except Exception as error:
                if strict:
                    strict_errors.append(error)

        if len(strict_errors) == 1:
            raise StrictCleanupError(str(strict_errors[0])) from strict_errors[0]
        if strict_errors:
            message = "; ".join(f"{type(error).__name__}: {error}" for error in strict_errors)
            raise StrictCleanupError(f"{len(strict_errors)} strict cleanup callbacks failed: {message}") from ExceptionGroup(
                "Strict cleanup callbacks failed", strict_errors
            )

