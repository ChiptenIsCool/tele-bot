"""Decorator-based logging (SPECS/TECH.md).

Logging is applied around functions rather than woven through business logic,
so handlers stay about behaviour and every path gets the same treatment.
"""

import functools
import logging
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any, TypeVar

R = TypeVar("R")


def _describe(value: Any) -> str:
    """Short, safe rendering of a value for a log line.

    Bytes are summarised rather than dumped — photos are megabytes and secrets
    must never be echoed into the log.
    """
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, str) and len(value) > 120:
        return value[:117] + "..."
    if isinstance(value, (int, float, bool, type(None))):
        return repr(value)
    return type(value).__name__


def _summarise(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    rendered = [_describe(a) for a in args]
    rendered += [f"{k}={_describe(v)}" for k, v in kwargs.items()]
    return ", ".join(rendered)


def log_call(
    logger: logging.Logger | None = None,
) -> Callable[[Callable[..., R]], Callable[..., R]]:
    """Log a call's arguments, its result, and any exception it raises.

    Exceptions are logged and re-raised — never swallowed, never left silent.
    """

    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        log = logger or logging.getLogger(func.__module__)
        name = f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> R:
            log.debug("call.start func=%s args=(%s)", name, _summarise(args, kwargs))
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                log.exception("call.failed func=%s error=%s: %s", name, type(exc).__name__, exc)
                raise
            log.debug("call.done func=%s result=(%s)", name, _describe(result))
            return result

        return wrapper

    return decorator


def log_async_call(
    logger: logging.Logger | None = None,
) -> Callable[[Callable[..., Coroutine[Any, Any, R]]], Callable[..., Coroutine[Any, Any, R]]]:
    """``log_call`` for coroutine functions."""

    def decorator(
        func: Callable[..., Coroutine[Any, Any, R]],
    ) -> Callable[..., Coroutine[Any, Any, R]]:
        log = logger or logging.getLogger(func.__module__)
        name = f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            log.debug("call.start func=%s args=(%s)", name, _summarise(args, kwargs))
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                log.exception("call.failed func=%s error=%s: %s", name, type(exc).__name__, exc)
                raise
            log.debug("call.done func=%s result=(%s)", name, _describe(result))
            return result

        return wrapper

    return decorator


def log_async_gen_call(
    logger: logging.Logger | None = None,
) -> Callable[[Callable[..., AsyncGenerator[Any, None]]], Callable[..., AsyncGenerator[Any, None]]]:
    """Log an async-generator call without breaking its generator-ness.

    Distinct from ``log_async_call`` because ADK (and Python) treat an async
    generator function differently from a coroutine function — wrapping one
    into the other silently changes the protocol.
    """

    def decorator(
        func: Callable[..., AsyncGenerator[Any, None]],
    ) -> Callable[..., AsyncGenerator[Any, None]]:
        log = logger or logging.getLogger(func.__module__)
        name = f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            log.debug("call.start func=%s args=(%s)", name, _summarise(args, kwargs))
            try:
                async for item in func(*args, **kwargs):
                    yield item
            except Exception as exc:
                log.exception("call.failed func=%s error=%s: %s", name, type(exc).__name__, exc)
                raise
            log.debug("call.done func=%s", name)

        return wrapper

    return decorator
