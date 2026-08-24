from src.execution.fake_exchange import FakeExchange


def test_fake_exchange_fill_fee_and_idempotency():
    venue = FakeExchange(fee_bps=10)
    first = venue.place_order("cid-1", "BTCUSDT", "BUY", 1, 100)
    second = venue.place_order("cid-1", "BTCUSDT", "BUY", 1, 100)
    assert first == second
    assert first.fee == 0.1
    assert venue.positions["BTCUSDT"].quantity == 1


def test_protection_readback():
    venue = FakeExchange()
    venue.place_order("cid-2", "BTCUSDT", "BUY", 1, 100)
    venue.set_protection("BTCUSDT", 95, 110)
    pos = venue.positions["BTCUSDT"]
    assert (pos.stop_loss, pos.take_profit) == (95, 110)


def test_opposite_order_closes_position():
    venue = FakeExchange()
    venue.place_order("open", "BTCUSDT", "BUY", 2, 100)
    venue.place_order("close", "BTCUSDT", "SELL", 2, 105)
    assert "BTCUSDT" not in venue.positions
