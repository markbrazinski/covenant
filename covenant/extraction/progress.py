from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator


ProgressSink = Callable[[str, dict[str, Any]], None]

_progress_sink: ContextVar[ProgressSink | None] = ContextVar(
    "covenant_extraction_progress_sink",
    default=None,
)


@contextmanager
def observe_extraction_progress(sink: ProgressSink) -> Iterator[None]:
    """Attach request-local observability without changing extraction inputs."""
    token = _progress_sink.set(sink)
    try:
        yield
    finally:
        _progress_sink.reset(token)


def emit_extraction_progress(
    phase: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Emit a best-effort progress event; observers cannot affect decisions."""
    sink = _progress_sink.get()
    if sink is None:
        return
    try:
        sink(phase, data or {})
    except Exception:
        # Progress is non-authoritative. Extraction and verification must behave
        # identically even when an observer is unavailable.
        return
