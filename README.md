# pocketfm-bot
# Pocket FM Stream Bot

A Telegram bot that:
1. Logs you into Pocket FM using your phone number + OTP
2. Extracts the CloudFront `.m3u8` stream URL from any episode or show

## Repo structure

```
bot.py              Telegram bot
pocketfm.py         Pocket FM OTP login + stream extraction
requirements.txt    Python dependencies
.github/
  workflows/
    run_bot.yml     GitHub Actions workflow
```

## Setup (5 minutes)

### 1. Create a Telegram bot
- Message [@BotFather](https://t.me/BotFather) on Telegram
- Send `/newbot` and follow the steps
- Copy the token it gives you

### 2. Add the token to GitHub
- Go to your repo → **Settings** → **Secrets and variables** → **Actions**
- Click **New repository secret**
- Name: `TELEGRAM_BOT_TOKEN`  |  Value: your bot token

### 3. Run the bot
- Go to the **Actions** tab → **Run Pocket FM Bot** → **Run workflow**

## Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Show all commands |
| `/login` | Log in with phone number + OTP |
| `/episode <url_or_slug>` | Get .m3u8 link for one episode |
| `/show <url_or_slug>` | Get .m3u8 links for all episodes of a show |
| `/token` | Show your current access token |
| `/logout` | Clear your saved token |
| `/cancel` | Cancel current action |

## Usage examples

```
/episode https://pocketfm.com/episode/214040b4ee41483f85758d4fca287b38
/episode 214040b4ee41483f85758d4fca287b38

/show https://pocketfm.com/show/mahagatha-9c8b7a
/show mahagatha-9c8b7a
```

## Notes

- You must log in (/login) before using /episode or /show
- Only episodes you have **purchased** will return stream URLs
- Tokens are stored in memory — you need to /login again if the bot restarts
