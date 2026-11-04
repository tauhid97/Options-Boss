"""PLAIN WORDS - every message Boss reads, written so a 5-year-old could follow it."""
import pandas as pd

from . import config as C

NAMES = {"SPY": "the S&P 500 (SPY)", "QQQ": "the Nasdaq 100 (QQQ)", "AAPL": "Apple (AAPL)",
         "TSLA": "Tesla (TSLA)", "NVDA": "Nvidia (NVDA)", "AMD": "AMD (AMD)", "MSFT": "Microsoft (MSFT)",
         "AMZN": "Amazon (AMZN)", "META": "Meta (META)", "GOOGL": "Google (GOOGL)"}


# The day-trade bot's skills, in kid words (a new skill it learns just uses its own reason).
KID = {
    "20-Day Breakout": "It's about to jump over its highest price of the whole month.",
    "Bull Flag": "It shot up like a rocket, rested, and is ready to take off again.",
    "Oversold Comeback": "It got knocked down hard yesterday and is climbing back today.",
    "Gap & Go": "It jumped up this morning and lots of people are buying.",
    "Gap-Down Bounce": "It fell off a cliff overnight and is bouncing back up.",
    "Hype Breakout": "Everyone on Reddit is talking about it, and it's going up.",
    "MA20 Reclaim": "It climbed back above its 'normal' line. Buyers are back.",
    "ORB Stocks in Play": "Everyone is crowding into it today, and it broke out of its morning box.",
    "Oversold Bounce": "A big stock fell too far, too fast, and is bouncing back.",
    "Relative Strength": "It's going UP while the rest of the market isn't.",
    "NR7 Breakout": "It barely moved yesterday, like a squished spring. Springs jump.",
    "Beaten-Down Turnaround": "It's been losing for months and is starting to bounce back.",
    "VWAP Pullback": "It's having a good day and dipped to its average price, like a sale.",
    "Downtrend Reversal": "It was sliding for months and suddenly woke up today.",
}


def kid_reason(skill_name, their_reason=None):
    return KID.get(skill_name) or str(their_reason or "The day-trade bot picked it.")


def name(t):
    return NAMES.get(t, t)


def money(x):
    x = float(x)
    return f"${x:,.2f}" if abs(x) < 100 else f"${x:,.0f}"


def price(x):
    """A stock price, always with cents (a buy price of $410.96 must not say $411)."""
    return f"${float(x):,.2f}"


def strike(x):
    return f"${x:g}"


def day(d):
    return f"{pd.Timestamp(d):%a %b} {pd.Timestamp(d).day}"


def cost(price):
    return price * 100 + C.FEE_PER_CONTRACT


def ticket_lines(i, t, reason, skill_name=None):
    kind = "Call" if t["side"] == "call" else "Put"
    bet = "keeps going UP" if t["side"] == "call" else "keeps going DOWN"
    arrow = "📈" if t["side"] == "call" else "📉"
    return [
        f"🎟️ TICKET {i}: {t['ticker']} {kind} (PRACTICE - pretend money)",
        *([f"🧠 Skill: {skill_name}"] if skill_name else []),
        f"{arrow} {reason}",
        f"We bet it {bet}.",
        "",
        "What to tap in Robinhood:",
        f"1️⃣ Search {name(t['ticker'])}",
        "2️⃣ Tap Trade, then Trade Options",
        f"3️⃣ At the top, pick Buy and {kind}",
        f"4️⃣ Pick the date {day(t['expiry'])}",
        f"5️⃣ Find the price {strike(t['strike'])} in the list and tap the +",
        f"6️⃣ Order type: Limit. Price: {money(t['buy_price'])}",
        f"7️⃣ Contracts: 1 (total cost about {money(cost(t['buy_price']))})",
        "8️⃣ Tap Review. 🛑 PRACTICE: stop here, don't swipe up!",
        "",
        f"✅ Sell when the price reaches {money(t['target'])} (we win)",
        f"🛑 Sell if it falls to {money(t['stop'])} (we stop the loss)",
        f"⏰ Sell by 3:30 pm no matter what",
        "⚠️ Tickets can go to $0.",
        "",
    ]


def _when(ts):
    return f"{ts:%a %b} {ts.day} (sent {ts:%I:%M %p} ET)".replace(" 0", " ")


LATE = "(Prices are from Yahoo and can be about 15 minutes late. Check the app's price.)"


def morning(tickets, ts, skipped=()):
    lines = [f"🌞 {C.BRAND_NAME} - {_when(ts)}", ""]
    if not tickets:
        lines += ["No Morning Breakout tickets right now. Nothing was clear enough. 👍", ""]
    for i, (t, why) in enumerate(tickets, 1):
        lines += ticket_lines(i, t, why, "Morning Breakout")
    for r in skipped:
        lines += [f"🙅 Skipped {r['ticker']}: {r['note']}.", ""]
    lines += ["Around 11:30 I'll also check the day-trade bot's picks. 👀"]
    if tickets:
        lines += [LATE]
    return "\n".join(lines)


def watching(rows):
    lines = [f"👀 The day-trade bot picked {len(rows)} stock{'s' if len(rows) != 1 else ''}. "
             "I'm watching them. Don't buy anything yet!", ""]
    for r in rows:
        how = "dips to" if r["wait_type"] == "buy_limit" else "climbs to"
        lines.append(f"• {name(r['ticker'])}, if it {how} {price(r['wait_price'])} ({r['skill']})")
    lines += ["", "If one gets there before 2 pm, I'll send you a Call ticket with the Robinhood steps."]
    return "\n".join(lines)


def buy_now(t, skill_name, reason, ts):
    lines = [f"🚨 {name(t['ticker'])} reached its buy price! ({_when(ts)})", ""]
    lines += ticket_lines(1, t, reason, skill_name)
    return "\n".join(lines + [LATE])


def skipped(row, why):
    return f"🙅 {name(row['ticker'])} reached its buy price, but I skipped the ticket: {why}. No trade is a good trade."


def pnl(t):
    """Pretend dollars won or lost on 1 contract, after Robinhood's small fees."""
    return (float(t["sell_price"]) - float(t["buy_price"])) * 100 - 2 * C.FEE_PER_CONTRACT


HOW = {"target": "reached the win price 🎉", "stop": "hit the stop 😢", "time": "sold at 3:30 pm ⏰"}


def closed(t):
    kind = "Call" if t["side"] == "call" else "Put"
    p = pnl(t)
    face = "won" if p > 0 else "lost"
    return (f"🔔 {t['ticker']} {kind} {HOW.get(t['status'], 'ended')}\n"
            f"Bought {money(t['buy_price'])}, sold {money(t['sell_price'])}.\n"
            f"We {face} {money(abs(p))} (pretend money, 1 contract). Practice only!")


def night(today, everything, no_buys=()):
    lines = ["🌙 Report card", ""]
    if not len(today):
        lines += ["No tickets today.", ""]
    else:
        lines.append(f"Today: {len(today)} ticket{'s' if len(today) > 1 else ''}")
        for _, t in today.iterrows():
            kind = "Call" if t["side"] == "call" else "Put"
            p = pnl(t)
            lines.append(f"{'🎉' if p > 0 else '😢'} {t['ticker']} {kind}: {'won' if p > 0 else 'lost'} {money(abs(p))}")
        lines.append(f"Today's total: {'+' if today_total(today) >= 0 else '-'}{money(abs(today_total(today)))}")
        lines.append("")
    lines += [f"🙅 {x}" for x in no_buys]
    if no_buys:
        lines.append("")
    lines += scoreboard(everything) + [""] + coach(everything)
    return "\n".join(lines)


def coach(done):
    """🧑‍🏫 Coach: how each skill is doing with option tickets."""
    if not len(done):
        return ["🧑‍🏫 Coach: no finished tickets yet, so no skill grades."]
    lines = ["🧑‍🏫 Coach (each skill's score):"]
    rows = []
    for sk, g in done.groupby(done["skill"].fillna("Morning Breakout")):
        total = today_total(g)
        wins = sum(pnl(t) > 0 for _, t in g.iterrows())
        rows.append((total, f"{'🟢' if total > 0 else '🔴'} {sk}: {len(g)} ticket{'s' if len(g) > 1 else ''}, "
                            f"{wins} won, {'+' if total >= 0 else '-'}{money(abs(total))}"))
    lines += [r for _, r in sorted(rows, reverse=True)]
    return lines


def today_total(df):
    return sum(pnl(t) for _, t in df.iterrows())


def scoreboard(done):
    if not len(done):
        return ["🏆 Scoreboard: no finished tickets yet.", "Everything is PRACTICE - pretend money."]
    wins = sum(pnl(t) > 0 for _, t in done.iterrows())
    total = today_total(done)
    return [f"🏆 Scoreboard (since the start): {len(done)} ticket{'s' if len(done) > 1 else ''}, "
            f"{wins} won, {len(done) - wins} lost",
            f"Total: {'+' if total >= 0 else '-'}{money(abs(total))} pretend money (1 contract each)",
            "Everything is PRACTICE. We watch for 2-3 months before any real money."]
