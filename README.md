# Options Boss: Boss's practice options bot

## The big idea (explained like you're 5)

An **option** is a ticket that bets a stock goes **up** (a **Call**) or **down** (a **Put**) before
a certain day. Tickets are cheap, but they can drop to **$0** fast.

Options Boss has two ways to find tickets:

1. **Morning Breakout** (its own skill, ~10:30 am New York time): if a big, busy stock (SPY, QQQ,
   Apple, Tesla...) breaks out of its "morning box" (the first 30 minutes) with lots of people
   trading it, and the whole market is going the same way, it sends a **Call** (going up) or a
   **Put** (going down). At most 2 a day.
2. **Day-trade skills** (~11:30 am): it copies the picks of Boss's day-trade bot (all of its skills,
   and any new ones it learns). It **waits** until the stock reaches the pick's buy price, then sends
   a **Call** ticket. If the stock never gets there by 2 pm, it skips it.

At most **4 tickets a day** in total, each with the exact buttons to tap in Robinhood.

### The option safety skills (every ticket must pass all 4)

| Skill | What it does |
|---|---|
| 🎯 Right ticket | Soonest end date 2-10 days away, strike price closest to the stock price |
| 👥 Busy enough | Only popular tickets with a small gap between the buy and sell price, under $1,000 |
| 🚫 Too pricey | Skips tickets priced for much bigger jumps than the stock really makes |
| 📅 Earnings day | Skips it if the company reports earnings before the ticket ends |

And the **🧑‍🏫 Coach** keeps a separate score for every skill (in the night report, on the page,
and with `/skills`).

**It never trades. It never uses real money.** Everything is PRACTICE: follow the steps, but
**stop at Review, don't swipe up.** We watch 2-3 months of live results before even thinking
about real money.

### Lessons from YouTube (tested 2026-11-04)

We watched 9 popular options videos and tested their rules on the last 2 months (estimated prices).
None of them helped, so they are all **switched off** in `optionsboss/config.py`. We can re-test them
later, when there's more data:

| Rule | Setting | Past test |
|---|---|---|
| 📏 Trend line: Calls only above the 200-day average, Puts only below | `TREND_FILTER` | Lost more per ticket |
| 🚧 No trading zone: skip if still inside yesterday's high-low range | `NO_TRADE_ZONE` | Lost more per ticket |
| 🔁 Don't chase: wait for the come-back to the box edge | `WAIT_FOR_RETEST` | Lost more per ticket |
| 💪 Strike one step "in the money" | `ITM_STEPS` | Mixed, no clear help |

Good lessons the bot **already** follows: no cheap "lottery" tickets, skip earnings, small price gaps,
same small size every time, and lots of practice tickets before any real money.

## What you'll get on Telegram (from your "Options Boss" bot)

| When | Message |
|---|---|
| ~10:30 am ET | 🌞 Morning Breakout tickets (or "none right now") with the Robinhood steps |
| ~11:30 am ET | 👀 The day-trade bot's picks I'm watching (don't buy yet!) |
| When a pick reaches its price | 🚨 "reached its buy price!" + a Call ticket with the Robinhood steps |
| A ticket is sold | 🔔 "AAPL Call reached the win price 🎉 ... We won $84" |
| ~4:15 pm ET | 🌙 Report card + scoreboard + Coach |

**You can ask the bot things** (it answers within about 15 minutes, on market days): `/status`,
`/tickets` (still open or waiting), `/scoreboard`, `/skills` (the Coach). It only answers you.

## The fair rules

1. We "buy" at the **ask** price (the higher one), and "sell" at the **bid** (the lower one).
2. Robinhood's small per-contract fees are taken off.
3. Sell at **+40%** (win), **-25%** (stop), or at **3:30 pm** no matter what.
4. Prices are checked every ~15 minutes and come from Yahoo (about 15 minutes late).

## Files

| File | What it is |
|---|---|
| `stocks.txt` | The stocks it looks at. Add or remove freely. |
| `optionsboss/skill.py` | The Morning Breakout skill (when to pick). |
| `optionsboss/copycat.py` | Copies the day-trade bot's picks and waits for their buy price. |
| `optionsboss/ticket.py` | Chooses the exact ticket (date + strike price) and runs the safety skills. |
| `optionsboss/plain.py` | Every message, in plain words. |
| `optionsboss/config.py` | All the settings. |
| `data/tickets.csv` | Every practice ticket and how it ended (the bot writes this). |
| `docs/index.html` | The scoreboard page (the bot writes this). |

## Costs

**Free**, as long as this GitHub project is **public**. (A private project would use up GitHub's
free minutes and could start charging.)

## Commands (Actions tab, then "Options Boss", then "Run workflow")

- `hello`: sends a test message to your Telegram
- `backtest`: practice on the last ~2 months, for both ways (ticket prices are estimated)
- `scoreboard`: sends the scoreboard right now
- `run`: one normal check

## Not financial advice

This is a learning tool. Options are the riskiest kind of trade, and most short-term option
buyers lose money.
