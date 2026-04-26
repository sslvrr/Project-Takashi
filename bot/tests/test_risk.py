"""
Unit tests for the risk management modules.
"""

import pytest
from risk.manager import position_size, allow_trade, check_daily_loss, check_max_positions
from risk.kill_switch import KillSwitch
from risk.scaling import capital_scale, scale_position
from risk.frequency import FrequencyGuard
from risk.portfolio import allocate_capital, risk_parity, exposure
from risk.equity_control import equity_filter
from core.metrics import sharpe_ratio, max_drawdown, win_rate, profit_factor


# ─── Position sizing ──────────────────────────────────────────────────────────

def test_position_size_positive():
    size = position_size(balance=10_000, price=0.52)
    assert size > 0


def test_position_size_zero_price():
    size = position_size(balance=10_000, price=0.0)
    assert size == 0.0


def test_allow_trade_blocks_after_3_losses():
    trades = [-10, -5, -8]
    assert not allow_trade(trades)


def test_allow_trade_allows_mixed():
    trades = [-10, 5, -8]
    assert allow_trade(trades)


def test_check_daily_loss_blocked():
    assert not check_daily_loss(daily_pnl=-600, balance=10_000)  # 6% > 5%


def test_check_daily_loss_allowed():
    assert check_daily_loss(daily_pnl=-400, balance=10_000)  # 4% < 5%


def test_check_max_positions():
    assert not check_max_positions(3)  # At limit
    assert check_max_positions(2)


# ─── Kill switch ─────────────────────────────────────────────────────────────

def test_kill_switch_not_triggered():
    ks = KillSwitch(max_drawdown=0.10)
    assert not ks.update(10_000)
    assert not ks.update(9_500)  # 5% drawdown


def test_kill_switch_triggers():
    ks = KillSwitch(max_drawdown=0.10)
    ks.update(10_000)
    assert ks.update(8_900)  # 11% drawdown → triggers


def test_kill_switch_latches():
    ks = KillSwitch(max_drawdown=0.10)
    ks.update(10_000)
    ks.update(8_900)
    assert ks.triggered
    assert ks.update(9_500)  # still triggered after partial recovery


def test_kill_switch_reset():
    ks = KillSwitch(max_drawdown=0.10)
    ks.update(10_000)
    ks.update(8_900)
    ks.reset()
    assert not ks.triggered


# ─── Capital scaling ─────────────────────────────────────────────────────────

def test_capital_scale_micro():
    assert capital_scale(5_000) == 0.10


def test_capital_scale_growing():
    assert capital_scale(25_000) == 0.30


def test_capital_scale_full():
    assert capital_scale(100_000) == 0.50


def test_scale_position():
    raw = 100.0
    scaled = scale_position(raw, equity=5_000)
    assert scaled == pytest.approx(10.0)


# ─── Frequency guard ─────────────────────────────────────────────────────────

def test_frequency_guard_allows_first():
    fg = FrequencyGuard(min_interval_seconds=60)
    assert fg.can_trade("XRP")


def test_frequency_guard_blocks_after_trade():
    fg = FrequencyGuard(min_interval_seconds=60)
    fg.record_trade("XRP")
    assert not fg.can_trade("XRP")


# ─── Portfolio ────────────────────────────────────────────────────────────────

def test_allocate_capital_sums_to_one():
    signals = ["XRP", "EURUSD"]
    vols = {"XRP": 0.05, "EURUSD": 0.008}
    weights = allocate_capital(signals, vols)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_allocate_capital_empty():
    assert allocate_capital([], {}) == {}


def test_exposure_total():
    positions = [
        {"symbol": "XRP", "size": 1000},
        {"symbol": "XRP", "size": 500},
        {"symbol": "EURUSD", "size": 200},
    ]
    total, by_asset = exposure(positions)
    assert total == 1700
    assert by_asset["XRP"] == 1500
    assert by_asset["EURUSD"] == 200


# ─── Equity control ──────────────────────────────────────────────────────────

def test_equity_filter_positive_recent():
    curve = [10.0, 15.0, 12.0, 18.0, 20.0] * 4
    assert equity_filter(curve)


def test_equity_filter_negative_recent():
    curve = [10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.5, 0.1]
    assert not equity_filter(curve)


# ─── Metrics ─────────────────────────────────────────────────────────────────

def test_sharpe_positive_series():
    returns = [0.01] * 50 + [-0.005] * 20
    sharpe = sharpe_ratio(returns)
    assert sharpe > 0


def test_max_drawdown_zero():
    equity = [10_000, 10_500, 11_000, 11_500]
    assert max_drawdown(equity) == 0.0


def test_max_drawdown_computed():
    equity = [10_000, 12_000, 8_000, 9_000]
    dd = max_drawdown(equity)
    assert dd == pytest.approx(1 / 3, rel=1e-3)


def test_win_rate():
    trades = [10, -5, 8, -3, 12]
    assert win_rate(trades) == pytest.approx(0.6)


def test_profit_factor():
    trades = [10, -5, 8, -2]
    pf = profit_factor(trades)
    assert pf == pytest.approx(18 / 7, rel=1e-3)
