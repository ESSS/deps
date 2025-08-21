"""
Helper module to create a synchronous executor to be used replacing the ThreadPoolExecutor
when running synchronously.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Future:
    def __init__(self, callback: Callable[..., Any], args: Any) -> None:
        try:
            self._result: Any | None = callback(*args)
            self._exception: Exception | None = None
        except Exception as err:
            self._result = None
            self._exception = err

    def cancelled(self) -> bool:
        return False

    def cancel(self) -> bool:
        return False

    def done(self) -> bool:
        return True

    def exception(self) -> Exception | None:
        return self._exception

    def result(self) -> Any:
        if self._exception is not None:
            raise self._exception
        else:
            return self._result

    def add_done_callback(self, callback: Callable[[Future], Any]) -> None:
        callback(self)


class SynchronousExecutor:
    """
    Synchronous executor: submit() blocks until it gets the result.
    """

    def submit(self, callback: Callable[..., Any], *args: Any) -> Future:
        return Future(callback, args)

    def shutdown(self, wait: bool) -> None:
        pass
