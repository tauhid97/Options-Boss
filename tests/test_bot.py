"""Quick checks that run without the internet:  python -m pytest tests  (or python tests/test_bot.py)"""
import os
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from optionsboss import backtest, bot, copycat, plain, skill, ticket
from optionsboss import config as C

NY = C.TIMEZONE


def fake_bars(moves, days=12):
    """days of flat 5-minute candles, then a last day that follows `moves` (one price per candle)."""
    rows = []
    for d in pd.bdate_range("2026-10-01", periods=days + 1):
        times = pd.date_range(d + pd.Timedelta(hours=9, minutes=30), periods=78, freq="5min", tz=NY)
        last = d == pd.bdate_range("2026-10-01", periods=days + 1)[-1]
        for i, t in enumerate(times):
            p = moves[min(i, len(moves) - 1)] if last else 100.0
            rows.append((t, p, p + 0.05, p - 0.05, p, 2000 if last else 1000))
    df = pd.DataFrame(rows, columns=["t", "Open", "High", "Low", "Close", "Volume"]).set_index("t")
    return df


def test_call_when_breaking_out_up():
    up = [100.0] * 6 + [100 + 0.2 * i for i in range(1, 40)]
    market = {"AAPL": fake_bars(up), "SPY": fake_bars(up)}
    ts = market["AAPL"].index[-1].normalize() + pd.Timedelta(hours=10, minutes=30)
    found = skill.find(market, ts)
    assert found and all(f["side"] == "call" for f in found)


def test_no_ticket_on_a_quiet_day():
    market = {"AAPL": fake_bars([100.0]), "SPY": fake_bars([100.0])}
    ts = market["AAPL"].index[-1].normalize() + pd.Timedelta(hours=10, minutes=30)
    assert skill.find(market, ts) == []


def test_never_against_the_market():
    up = [100.0] * 6 + [100 + 0.2 * i for i in range(1, 40)]
    down = [100.0] * 6 + [100 - 0.2 * i for i in range(1, 40)]
    market = {"AAPL": fake_bars(up), "SPY": fake_bars(down)}
    ts = market["AAPL"].index[-1].normalize() + pd.Timedelta(hours=10, minutes=30)
    assert all(f["ticker"] != "AAPL" for f in skill.find(market, ts))


def test_sell_rules():
    t = {"target": 1.40, "stop": 0.75}
    assert bot.check(t, {"bid": 1.45}, "11:00") == ("target", 1.45)
    assert bot.check(t, {"bid": 0.70}, "11:00") == ("stop", 0.70)
    assert bot.check(t, {"bid": 1.00}, "15:30") == ("time", 1.00)
    assert bot.check(t, {"bid": 1.00}, "11:00") is None
    assert bot.check(t, {"bid": 0}, "15:45") is None          # no price = don't guess


def test_strike_picker_skips_bad_tickets():
    df = pd.DataFrame({"contractSymbol": ["A", "B", "C"], "strike": [99, 100, 101],
                       "bid": [2.0, 1.0, 1.5], "ask": [2.1, 1.5, 1.55], "openInterest": [900, 900, 10]})
    # B is closest but has a wide gap; C is popular-ish? no (10) -> A wins
    assert ticket.pick_strike(df, 100.2)["contractSymbol"] == "A"


def test_expiry_picker():
    today = pd.Timestamp("2026-11-03 10:30", tz=NY)
    assert ticket.pick_expiry(["2026-11-03", "2026-11-04", "2026-11-06", "2026-11-13"], today) == "2026-11-06"
    assert ticket.pick_expiry(["2026-11-03", "2026-12-18"], today) is None


def test_money_after_fees():
    assert round(plain.pnl({"buy_price": 2.00, "sell_price": 2.80}), 2) == 79.92


def test_black_scholes_sane():
    c = backtest.fair_price("call", 100, 100, 5 / 365, 0.3)
    p = backtest.fair_price("put", 100, 100, 5 / 365, 0.3)
    assert 0.5 < c < 2 and abs(c - p) < 0.01
    assert backtest.fair_price("call", 105, 100, 0, 0.3) == 5


def test_message_is_kid_simple():
    t = {"ticker": "AAPL", "side": "put", "expiry": "2026-11-06", "strike": 230.0, "buy_price": 2.1,
         "target": 2.94, "stop": 1.58}
    text = "\n".join(plain.ticket_lines(1, t, "Apple is going DOWN today."))
    for must in ["Put", "Fri Nov 6", "$230", "Limit", "$2.10", "about $210", "don't swipe up", "Sell by 3:30"]:
        assert must in text, must


def test_full_day_on_paper(monkeypatch=None):
    """scan -> track -> night with fake prices, in a throwaway folder."""
    sent = []
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            open("stocks.txt", "w").write("AAPL\n")
            up = [100.0] * 6 + [100 + 0.2 * i for i in range(1, 40)]
            bars = {"AAPL": fake_bars(up), "SPY": fake_bars(up)}
            day = bars["AAPL"].index[-1].normalize()
            bot.data.intraday = lambda tickers, **k: bars
            bot.data.expirations = lambda t: [f"{day + pd.Timedelta(days=3):%Y-%m-%d}"]
            bot.data.chain = lambda t, e, s: pd.DataFrame({"contractSymbol": ["X"], "strike": [104.0],
                                                           "bid": [1.95], "ask": [2.00], "openInterest": [5000]})
            bot.data.earnings_dates = lambda t: []
            bot.data.jumpiness = lambda t: 0.6
            bot.send = lambda text: sent.append(text) or True
            bot.scan(ts=day + pd.Timedelta(hours=10, minutes=30))
            assert "TICKET 1: AAPL Call" in sent[-1]
            bot.data.quote = lambda *a: {"bid": 2.85, "ask": 2.9, "last": 2.87}
            bot.track(ts=day + pd.Timedelta(hours=11))
            assert "reached the win price" in sent[-1]
            bot.night(ts=day + pd.Timedelta(hours=16, minutes=30))
            assert "Report card" in sent[-1] and "won" in sent[-1]
            n = len(sent)
            bot.night(ts=day + pd.Timedelta(hours=16, minutes=45))   # only once a night
            assert len(sent) == n
        finally:
            os.chdir(old)


def test_copies_live_picks_first_and_skips_repeats():
    picks = pd.DataFrame({"date": ["2026-11-03"] * 4 + ["2026-11-02"],
                          "mode": ["practice", "live", "practice", "live", "live"],
                          "ticker": ["HUT", "NVDA", "NVDA", "ORCL", "OLD"],
                          "setup": ["Downtrend Reversal", "VWAP Pullback", "20-Day Breakout", "VWAP Pullback", "X"],
                          "order_type": ["buy_stop", "buy_limit", "buy_stop", "buy_limit", "buy_stop"],
                          "entry": [64.14, 208.04, 209.0, 124.96, 1.0]})
    got = copycat.todays_picks(picks, "2026-11-03", have={"ORCL"})
    assert [p["ticker"] for p in got] == ["NVDA", "HUT"]


def _wait_row(kind, price):
    return {"sent_at": "2026-11-03T11:30:00-05:00", "wait_type": kind, "wait_price": price}


def test_buy_price_reached():
    t = pd.date_range("2026-11-03 11:00", periods=8, freq="5min", tz=NY)
    bars = pd.DataFrame({"Open": 100.0, "High": [105, 100, 100, 100, 100, 100, 102, 100],
                         "Low": [95, 99, 99, 99, 99, 99, 99, 97], "Close": 100.0, "Volume": 1}, index=t)
    ts = pd.Timestamp("2026-11-03 11:50", tz=NY)
    assert copycat.reached(_wait_row("buy_stop", 101.5), bars, ts) == 100.0       # the 11:30 candle got there
    assert copycat.reached(_wait_row("buy_stop", 103), bars, ts) is None          # the 11:00 high was BEFORE the pick
    assert copycat.reached(_wait_row("buy_stop", 101.5), bars, pd.Timestamp("2026-11-03 11:30", tz=NY)) is None
    assert copycat.reached(_wait_row("buy_limit", 97.5), bars, pd.Timestamp("2026-11-03 11:38", tz=NY)) is None  # not finished
    assert copycat.reached(_wait_row("buy_limit", 97.5), bars, pd.Timestamp("2026-11-03 11:40", tz=NY)) == 100.0


def test_too_pricey_and_earnings():
    yrs = 5 / 365
    fair = ticket.fair_price("call", 100, 100, yrs, 0.30)
    assert abs(ticket.implied_jump("call", 100, 100, yrs, fair) - 0.30) < 0.001
    assert not ticket.too_pricey("call", 100, 100, yrs, fair, 0.30)
    assert ticket.too_pricey("call", 100, 100, yrs, ticket.fair_price("call", 100, 100, yrs, 0.80), 0.30)
    assert not ticket.too_pricey("call", 100, 100, yrs, fair * 3, None)          # unknown -> don't block
    today = pd.Timestamp("2026-11-03 11:00", tz=NY)
    assert ticket.earnings_before([pd.Timestamp("2026-11-05")], today, "2026-11-06")
    assert not ticket.earnings_before([pd.Timestamp("2026-11-09"), pd.Timestamp("2026-10-30")], today, "2026-11-06")


def test_coach_grades_each_skill():
    done = pd.DataFrame({"skill": ["VWAP Pullback", "VWAP Pullback", None],
                         "buy_price": [1.0, 1.0, 2.0], "sell_price": [1.4, 0.75, 1.5]})
    text = "\n".join(plain.coach(done))
    assert "VWAP Pullback: 2 tickets, 1 won, +$14.84" in text and "🔴 Morning Breakout: 1 ticket, 0 won" in text


def test_full_day_with_a_day_trade_pick():
    """Morning scan finds nothing -> copy the day-trade pick -> it reaches its price -> Call -> sold -> Coach."""
    sent = []
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            open("stocks.txt", "w").write("AAPL\n")
            flat = {"AAPL": fake_bars([100.0]), "SPY": fake_bars([100.0])}
            day = flat["AAPL"].index[-1].normalize()
            nv = fake_bars([100.0] * 26 + [100.0 + 0.1 * i for i in range(1, 40)])   # climbs after 11:40
            bot.data.intraday = lambda tickers, **k: {**flat, "NVDA": nv}
            bot.data.day_trade_picks = lambda: pd.DataFrame({
                "date": [f"{day:%Y-%m-%d}"], "published_at": [(day + pd.Timedelta(hours=11, minutes=30)).isoformat()], "mode": ["live"],
                "ticker": ["NVDA"], "setup": ["VWAP Pullback"], "order_type": ["buy_stop"], "entry": [100.5],
                "reason": ["Up 3% on 4x volume"]})
            bot.data.expirations = lambda t: [f"{day + pd.Timedelta(days=3):%Y-%m-%d}"]
            bot.data.chain = lambda t, e, s: pd.DataFrame({"contractSymbol": ["NV"], "strike": [101.0],
                                                           "bid": [1.95], "ask": [2.00], "openInterest": [5000]})
            bot.data.earnings_dates = lambda t: []
            bot.data.jumpiness = lambda t: 0.6
            bot.send = lambda text: sent.append(text) or True
            at = lambda h, m: day + pd.Timedelta(hours=h, minutes=m)
            bot.scan(ts=at(10, 30))
            assert "No Morning Breakout tickets" in sent[-1]
            bot.copy_picks(ts=at(10, 50))                       # too early
            assert len(sent) == 1
            bot.copy_picks(ts=at(11, 45))
            assert "Nvidia (NVDA), if it climbs to $100.50" in sent[-1] and "Don't buy anything yet" in sent[-1]
            bot.copy_picks(ts=at(12, 0))                        # only once a day
            assert len(sent) == 2
            bot.watch(ts=at(11, 45))                            # hasn't reached it yet
            assert len(sent) == 2
            bot.watch(ts=at(12, 15))
            assert "reached its buy price" in sent[-1] and "TICKET 1: NVDA Call" in sent[-1] and "VWAP Pullback" in sent[-1]
            bot.data.quote = lambda *a: {"bid": 1.40, "ask": 1.45, "last": 1.42}
            bot.track(ts=at(13, 0))
            assert "hit the stop" in sent[-1]
            bot.night(ts=at(16, 30))
            assert "Coach" in sent[-1] and "VWAP Pullback: 1 ticket, 0 won" in sent[-1]
            df = bot.load_tickets()
            assert list(df["status"]) == ["stop"]
        finally:
            os.chdir(old)


def test_waiting_pick_missed_after_2pm():
    df = pd.DataFrame([{"date": "2026-11-03", "ticker": "X", "status": "waiting", "wait_type": "buy_stop",
                        "wait_price": 1.0, "sent_at": "2026-11-03T11:30:00-05:00", "skill": "Bull Flag", "note": None}])
    out = copycat.watch(df, pd.Timestamp("2026-11-03 14:05", tz=NY), send=lambda t: None)
    assert out.at[0, "status"] == "missed"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
