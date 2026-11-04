"""All the settings for Options Boss. Everything is PRACTICE - no real money."""

BRAND_NAME = "Options Boss"
TIMEZONE = "America/New_York"

STOCKS_FILE = "stocks.txt"
TICKETS_FILE = "data/tickets.csv"
COMMANDS_STATE_FILE = "data/commands_state.json"
NIGHT_STATE_FILE = "data/night_state.json"
REPORT_FILE = "docs/index.html"
MARKET_TICKER = "SPY"          # the whole market's mood; it can also get a ticket

# --- Timing (US/Eastern) ---
OPENING_RANGE_END = "10:00"    # the first 30 minutes set the "morning box"
SCAN_START = "10:15"           # look for tickets from here...
SCAN_END = "11:30"             # ...until here (once a day)
SELL_BY = "15:30"              # sell anything still open at 3:30 pm
NIGHT_REPORT_AFTER = "16:15"   # nightly report card

# --- How it picks (the "Morning Breakout" skill) ---
MIN_MOVE_PCT = 0.5             # stock must be up/down at least 0.5% from yesterday's close
MIN_RVOL = 1.0                 # and trading at least as busy as usual
MAX_BREAKOUT_TICKETS = 2       # Morning Breakout gives at most 2 tickets a day
MAX_TICKETS_PER_DAY = 4        # all skills together: at most 4 tickets bought a day

# --- The day-trade bot's skills (Options Boss copies its daily picks) ---
PICKS_URL = "https://raw.githubusercontent.com/tauhid97/day-trade-picks/main/data/picks.csv"
COPY_FROM = "11:00"            # look for the day-trade bot's picks from here...
COPY_UNTIL = "13:00"           # ...until here
MAX_COPIED_PICKS = 5           # watch at most 5 of its picks a day ("live" ones first)
BUY_BY = "14:00"               # if a stock never reaches its buy price by 2 pm, skip it

# --- Which ticket (option) to choose ---
MIN_DAYS_LEFT = 2              # skip tickets ending today/tomorrow (they melt too fast)
MAX_DAYS_LEFT = 10
MAX_SPREAD_PCT = 10.0          # skip tickets where buy and sell prices are far apart
MIN_OPEN_INTEREST = 500        # only popular tickets
MAX_TICKET_COST = 1000         # skip tickets costing more than $1,000 for 1 contract

# --- Option safety skills ---
MAX_PRICEY = 1.8               # "Too pricey": skip if the ticket is priced for 1.8x more jumping than the stock really does
SKIP_EARNINGS = True           # "Earnings day": skip if the company reports earnings before the ticket ends

# --- When to sell ---
TARGET_PCT = 40                # sell when the ticket grows 40%
STOP_PCT = 25                  # sell if it shrinks 25%
FEE_PER_CONTRACT = 0.04        # Robinhood's small per-contract fees, each way (about)
