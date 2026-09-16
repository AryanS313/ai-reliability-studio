"""Content-free admission controls for the bounded native hosted beta.

These limits protect one application process. They are not distributed abuse
prevention, durable usage billing, or a substitute for managed ingress.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, TypeVar, cast
from weakref import WeakKeyDictionary, WeakSet

from src import config
from src.domain import ExecutionStatus, TargetResponse

HOSTED_MAX_EXECUTIONS = 100
HOSTED_MAX_CONCURRENCY = 2
HOSTED_MAX_RETRIES = 1
HOSTED_MAX_TIMEOUT_SECONDS = 30.0
HOSTED_MAX_OUTPUT_TOKENS = 4096
HOSTED_MAX_REQUEST_BYTES = 1024 * 1024
HOSTED_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
HOSTED_MAX_SESSION_DATABASE_BYTES = 16 * 1024 * 1024
HOSTED_MAX_ACTIVE_SESSIONS = 16
HOSTED_MAX_PROCESS_CALLS = 4
HOSTED_MAX_PROCESS_RUNS = 4
HOSTED_RATE_WINDOW_SECONDS = 600.0
HOSTED_SESSION_CALLS_PER_WINDOW = 200
HOSTED_PROCESS_CALLS_PER_WINDOW = 800


class HostedLimitError(ValueError):
    """A safe, actionable capacity message with no user content or credentials."""


@dataclass(eq=False)
class SessionBudget:
    calls: deque[float] = field(default_factory=deque)
    active_calls: int = 0
    active_run: bool = False
    closed: bool = False

    def close(self) -> None:
        with _lock:
            self.closed = True
            self.calls.clear()
            _sessions.discard(self)


_lock = threading.RLock()
_sessions: WeakSet[SessionBudget] = WeakSet()
_repository_budgets: WeakKeyDictionary[Any, SessionBudget] = WeakKeyDictionary()
_current: ContextVar[SessionBudget | None] = ContextVar("studio_hosted_budget", default=None)
_process_calls: deque[float] = deque()
_active_calls = 0
_active_runs = 0
F = TypeVar("F", bound=Callable[..., Any])


def run_limit_notice() -> str:
    return (
        f"Online reviews support up to {HOSTED_MAX_EXECUTIONS} answers (questions × versions), "
        f"{HOSTED_MAX_CONCURRENCY} calls at once and {HOSTED_MAX_RETRIES} retry after a temporary error. "
        f"Each call has a {HOSTED_MAX_TIMEOUT_SECONDS:g}-second timeout."
    )


def new_session_budget() -> SessionBudget:
    with _lock:
        if len(_sessions) >= HOSTED_MAX_ACTIVE_SESSIONS:
            raise HostedLimitError("The online workspace is at capacity. Please try again later.")
        budget = SessionBudget()
        _sessions.add(budget)
        return budget


def bind_session(budget: SessionBudget | None) -> None:
    _current.set(budget)


def bind_repository(repository: Any, budget: SessionBudget | None) -> None:
    if budget is not None:
        with _lock:
            _repository_budgets[repository] = budget


def repository_budget(repository: Any) -> SessionBudget | None:
    with _lock:
        return _repository_budgets.get(repository)


def current_session() -> SessionBudget | None:
    return _current.get() if config.hosted_sessions_enabled() else None


def _require_session(budget: SessionBudget | None) -> SessionBudget:
    if budget is None or budget.closed:
        raise HostedLimitError("This online session has expired. Reload the page to start a new workspace.")
    return budget


@contextmanager
def session_scope(budget: SessionBudget | None) -> Iterator[None]:
    if not config.hosted_sessions_enabled():
        yield
        return
    _require_session(budget)
    token = _current.set(budget)
    try:
        yield
    finally:
        _current.reset(token)


def validate_execution_limits(count: int, concurrency: int, retries: int | None) -> None:
    if not config.hosted_sessions_enabled():
        return
    _require_session(_current.get())
    if count > HOSTED_MAX_EXECUTIONS:
        raise HostedLimitError(run_limit_notice())
    if concurrency > HOSTED_MAX_CONCURRENCY or (retries is not None and retries > HOSTED_MAX_RETRIES):
        raise HostedLimitError(run_limit_notice())


def validate_provider_request(text: str, max_tokens: int) -> None:
    if not config.hosted_sessions_enabled():
        return
    _require_session(_current.get())
    if len(text.encode("utf-8")) > HOSTED_MAX_REQUEST_BYTES:
        raise HostedLimitError("The selected inputs exceed the online request limit. Use fewer source passages.")
    if type(max_tokens) is not int or not 1 <= max_tokens <= HOSTED_MAX_OUTPUT_TOKENS:
        raise HostedLimitError(f"Online provider calls allow 1–{HOSTED_MAX_OUTPUT_TOKENS} output tokens.")


@contextmanager
def call_scope(budget: SessionBudget | None = None) -> Iterator[None]:
    """Count every attempted network call, including health checks and retries."""
    global _active_calls
    if not config.hosted_sessions_enabled():
        yield
        return
    with _lock:
        session = _require_session(budget or _current.get())
        now = time.monotonic()
        cutoff = now - HOSTED_RATE_WINDOW_SECONDS
        for history in (session.calls, _process_calls):
            while history and history[0] <= cutoff:
                history.popleft()
        if session.active_calls >= HOSTED_MAX_CONCURRENCY or _active_calls >= HOSTED_MAX_PROCESS_CALLS:
            raise HostedLimitError("The online service is busy. Wait for the current calls to finish and try again.")
        if len(session.calls) >= HOSTED_SESSION_CALLS_PER_WINDOW:
            raise HostedLimitError(
                "This session has reached its 10-minute call limit. Please wait before trying again."
            )
        if len(_process_calls) >= HOSTED_PROCESS_CALLS_PER_WINDOW:
            raise HostedLimitError("The online service has reached its short-term call limit. Please try again later.")
        session.calls.append(now)
        _process_calls.append(now)
        session.active_calls += 1
        _active_calls += 1
    try:
        yield
    finally:
        with _lock:
            session.active_calls -= 1
            _active_calls -= 1


@contextmanager
def run_scope() -> Iterator[None]:
    global _active_runs
    if not config.hosted_sessions_enabled():
        yield
        return
    with _lock:
        session = _require_session(_current.get())
        if session.active_run:
            raise HostedLimitError("An evaluation is already running in this session. Wait for it to finish.")
        if _active_runs >= HOSTED_MAX_PROCESS_RUNS:
            raise HostedLimitError("The online service is busy with other evaluations. Please try again later.")
        session.active_run = True
        _active_runs += 1
    try:
        yield
    finally:
        with _lock:
            session.active_run = False
            _active_runs -= 1


def guard_run(function: F) -> F:
    @wraps(function)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        with run_scope():
            return function(*args, **kwargs)

    return cast(F, guarded)


def limit_response(error: HostedLimitError) -> TargetResponse:
    return TargetResponse(
        status=ExecutionStatus.RATE_LIMITED,
        error_code="hosted_capacity_limit",
        safe_error=str(error),
        metadata={"quality_score_eligible": False, "retryable": False, "network_checked": False},
    )


def guard_target_call(function: F) -> F:
    @wraps(function)
    def guarded(target: Any, *args: Any, **kwargs: Any) -> Any:
        if not config.hosted_sessions_enabled():
            return function(target, *args, **kwargs)
        try:
            with session_scope(target._hosted_budget), call_scope():
                return function(target, *args, **kwargs)
        except HostedLimitError as error:
            return limit_response(error)

    return cast(F, guarded)
