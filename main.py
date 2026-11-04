"""Command center for Options Boss.

  python main.py run            # the 15-minute routine (used by the schedule): tickets, day-trade picks, selling, report card
  (every run also answers Boss's /status, /tickets and /scoreboard messages to the bot)
  python main.py hello          # send a test message to your Options Boss Telegram
  python main.py scan --force   # look for tickets right now, even outside 10:15-11:30
  python main.py backtest       # practice on the last ~2 months (prints the results, also sends them)
  python main.py scoreboard     # send the scoreboard to your Telegram now
  python main.py report         # rebuild the scoreboard page
"""
import sys

from optionsboss import backtest, bot, commands, plain, report
from optionsboss import config as C
from optionsboss.notify import send


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        for name, job in [("Selling check", bot.track), ("Ticket scan", bot.scan),
                          ("Day-trade picks", bot.copy_picks), ("Buy-price check", bot.watch),
                          ("Report card", bot.night), ("Scoreboard page", report.build),
                          ("Commands", commands.handle)]:
            try:                       # one hiccup must never stop the rest
                job()
            except Exception as e:
                print(name, "skipped:", e)
    elif cmd == "hello":
        ok = send(f"Hi Boss! {C.BRAND_NAME} is connected. Practice option tickets will show up here "
                  "on market days around 10:30 am ET.")
        print("Sent!" if ok else "Telegram secrets are missing - see README.")
    elif cmd == "scan":
        bot.scan(force="--force" in sys.argv)
    elif cmd == "backtest":
        _, text = backtest.run()
        _, text2 = backtest.run_copied()
        print(text, "\n\n", text2)
        send("Boss, here's the Options Boss practice-on-the-past check:\n" + text + "\n\n" + text2)
    elif cmd == "scoreboard":
        df = bot.load_tickets()
        done = df[df["status"].isin(bot.FINISHED)] if len(df) else df
        send("\n".join(plain.scoreboard(done) + [""] + plain.coach(done)))
    elif cmd == "report":
        report.build()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
