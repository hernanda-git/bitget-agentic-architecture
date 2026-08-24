import asyncio

from src.runtime.scheduler import PaperScheduler


class Runtime:
    def __init__(self):
        self.calls = []

    async def process(self, snapshot, portfolio=None, now_ts_ms=None):
        self.calls.append(snapshot)
        await asyncio.sleep(0)
        return {"status": "HELD", "cycle_id": snapshot.snapshot_hash}


class Snap:
    def __init__(self, symbol, digest):
        self.symbol = symbol
        self.snapshot_hash = digest


def test_scheduler_coalesces_duplicate_snapshots_and_serializes_symbol():
    runtime = Runtime()
    scheduler = PaperScheduler(runtime, min_interval_seconds=0)
    a = Snap("BTCUSDT", "same")
    assert scheduler.enqueue(a) is True
    assert scheduler.enqueue(a) is False
    assert asyncio.run(scheduler.run_once()) == 1
    assert len(runtime.calls) == 1


def test_scheduler_parks_breaker_result_but_keeps_running():
    class ParkRuntime(Runtime):
        async def process(self, snapshot, portfolio=None, now_ts_ms=None):
            self.calls.append(snapshot)
            return {"status": "PARKED_PROVIDER", "cycle_id": snapshot.snapshot_hash}
    scheduler = PaperScheduler(ParkRuntime(), min_interval_seconds=0)
    scheduler.enqueue(Snap("ETHUSDT", "x"))
    assert asyncio.run(scheduler.run_once()) == 1
    assert scheduler.parked["ETHUSDT"] == "PARKED_PROVIDER"
    assert scheduler.running is True
