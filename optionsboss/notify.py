"""MESSENGER - sends messages from the Options Boss Telegram bot to Boss.

GitHub secrets (Settings -> Secrets and variables -> Actions):
  TELEGRAM_BOT_TOKEN   the Options Boss bot's token (from @BotFather)
  TELEGRAM_CHAT_ID     Boss's personal ID (from @userinfobot)
"""
import os

import requests


def send(text):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        print("(Telegram secrets missing - message not sent)")
        return False
    for i in range(0, len(text), 4000):
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": text[i:i + 4000], "disable_web_page_preview": True},
                          timeout=20)
        if not r.ok:
            print("Telegram error:", r.text[:200])
    return True
