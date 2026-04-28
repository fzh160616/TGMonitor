from tg_monitor.tg_client import _reconnect_delay


def test_reconnect_delay_starts_at_5():
    assert _reconnect_delay(0) == 5


def test_reconnect_delay_doubles():
    assert _reconnect_delay(1) == 10
    assert _reconnect_delay(2) == 20


def test_reconnect_delay_caps_at_120():
    assert _reconnect_delay(10) == 120
