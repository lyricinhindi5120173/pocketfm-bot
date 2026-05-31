Pocket FM browser-session version

What changed:
- Removed OTP API login flow from bot.py.
- Added pocketfm_browser.py using Playwright persistent Chromium profile.
- You log in manually once in Chromium; the bot reuses that saved session.

Setup on VPS/local PC with GUI or VNC:
1. pip install -r requirements.txt
2. playwright install chromium
3. export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
4. python pocketfm_browser.py --login
5. Log in to Pocket FM in the opened Chromium window.
6. Close browser after login.
7. python bot.py
8. In Telegram: /episode <episode_url_or_slug>

Environment variables:
- TELEGRAM_BOT_TOKEN: required
- POCKETFM_PROFILE_DIR: default pocketfm_profile
- POCKETFM_HEADLESS: true by default. Use false for debugging.

Important:
- Do not commit pocketfm_profile to public GitHub. It contains login cookies.
- Render/GitHub Actions are not good for first-time manual login because they do not provide a normal GUI browser session.
- Use only for content your own account is authorized to access.
