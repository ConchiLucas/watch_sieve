"""Cooperative cancellation shared by the scheduler and fetch engines."""
from collections.abc import Callable


class RefreshCancelled(RuntimeError):
    pass


def check_cancelled(should_stop: Callable[[], bool] | None) -> None:
    if should_stop is not None and should_stop():
        raise RefreshCancelled("抓取已停止")
