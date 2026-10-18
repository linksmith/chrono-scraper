"""
run_async_in_sync gives every call a fresh loop and empties the shared async engine's
pool on that loop before closing it, so pooled asyncpg connections never outlive
their loop ("Event loop is closed" / "attached to a different loop" in session 30).
"""
import asyncio

import pytest

from app.core import database
from app.tasks.firecrawl_scraping import run_async_in_sync


class RecordingEngine:
    def __init__(self, fail: bool = False):
        self.disposed_on = []
        self.fail = fail

    async def dispose(self):
        self.disposed_on.append(asyncio.get_running_loop())
        if self.fail:
            raise RuntimeError("dispose failed")


@pytest.fixture
def engine(monkeypatch):
    fake = RecordingEngine()
    monkeypatch.setattr(database, "engine", fake)
    return fake


def test_pool_is_released_on_the_loop_that_ran_the_coroutine(engine):
    async def work():
        return asyncio.get_running_loop()

    loop = run_async_in_sync(work())
    assert engine.disposed_on == [loop]
    assert loop.is_closed()


def test_each_call_gets_its_own_loop_and_its_own_release(engine):
    async def work():
        return asyncio.get_running_loop()

    first = run_async_in_sync(work)
    second = run_async_in_sync(work)
    assert first is not second
    assert engine.disposed_on == [first, second]


def test_pool_is_released_when_the_coroutine_raises(engine):
    async def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        run_async_in_sync(boom())
    assert len(engine.disposed_on) == 1


def test_a_failing_release_does_not_hide_the_result(monkeypatch):
    monkeypatch.setattr(database, "engine", RecordingEngine(fail=True))

    async def work():
        return 42

    assert run_async_in_sync(work()) == 42


def test_non_awaitable_is_rejected():
    with pytest.raises(TypeError):
        run_async_in_sync(lambda: 1)
