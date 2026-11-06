"""🧑‍🏫 COACH RULES - quick to bench, slow to trust. Everything stays PRACTICE.

Explained like you're 5:
  Every skill gets a grade from its last 10 practice tickets.
  🪑 Benched: its first 3+ tickets lost on average (below -0.10R). It keeps practicing, but its
     tickets come as short one-liners and go last in line.
  ⭐ Trusted: 5+ tickets that won on average (above +0.10R). Its tickets go first in line.
  🌱 Learning: everyone else.
  Trusted does NOT mean real money. That still needs 2-3 months of good live practice.
"""
from . import config as C
from . import plain

BENCHED, TRUSTED, LEARNING = "benched", "trusted", "learning"
BADGE = {BENCHED: "🪑 benched", TRUSTED: "⭐ trusted", LEARNING: "🌱 learning"}


def r_of(t):
    """One ticket's score: dollars won/lost divided by what the stop would lose (1R)."""
    risk = float(t["buy_price"]) * 100 * C.STOP_PCT / 100 + 2 * C.FEE_PER_CONTRACT
    return plain.pnl(t) / risk if risk > 0 else 0.0


def grade(done, skill_name):
    """'benched', 'trusted' or 'learning' for one skill, from its finished tickets."""
    if done is None or not len(done):
        return LEARNING
    g = done[done["skill"].fillna("Morning Breakout") == skill_name]
    if "sold_at" in g and g["sold_at"].notna().any():
        g = g.sort_values("sold_at", kind="stable")
    g = g.tail(C.COACH_LAST)
    if not len(g):
        return LEARNING
    avg = sum(r_of(t) for _, t in g.iterrows()) / len(g)
    if len(g) >= C.TRUST_AFTER and avg > C.TRUST_ABOVE:
        return TRUSTED
    if len(g) >= C.BENCH_AFTER and avg < C.BENCH_BELOW:
        return BENCHED
    return LEARNING


def grades(done):
    names = set(done["skill"].fillna("Morning Breakout")) if done is not None and len(done) else set()
    return {n: grade(done, n) for n in names}
