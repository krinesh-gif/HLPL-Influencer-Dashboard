# Aravi Instagram First Outreach — desktop prototype

This is a source-code prototype, not a live-verified Instagram integration. It attempts first DMs from a reviewed list; your team handles replies in Instagram. Instagram UI changes can require selector updates. It stops rather than guessing when sender, recipient or controls cannot be verified. No account safety or delivery guarantee.

## Setup (Windows or macOS)

Install Python 3.11 or newer from python.org. On Windows select Add Python to PATH. Extract this folder, open Terminal / Command Prompt inside it, then run:

```
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

On macOS use `python3` if `python` is unavailable. Tkinter is included with the standard python.org desktop installer. Linux needs a graphical desktop and tkinter installed separately.

## Daily workflow

1. Enter your sending Instagram username.
2. Import `.xlsx` / CSV with complete Instagram profile URLs, or paste one profile link per line. Excel reads the active sheet; hyperlink-only labels are not supported. Google Sheets: download as Excel or CSV first. Direct Sheets sync is not included.
3. Enter your approved introduction. Maximum 25 recipients per batch is a product limit, not an Instagram safe limit.
4. Click **Open login browser**. Log in manually, handle 2FA yourself, and set Instagram language to English. No passwords are collected by the app. A dedicated browser session is stored locally.
5. Click **Prepare one draft**. This navigates to the first eligible conversation and fills the message without pressing Send. Confirm the recipient and message. Clear that draft manually before starting the batch.
6. Click **Start batch**, review the exact sender, recipients and message, then confirm. The app attempts sends automatically. Keep the browser open and do not navigate it during a batch.
7. Use **Stop** to stop before the next send. An in-progress send may complete. Review results and replies directly in Instagram.
8. Export the results as CSV.

## Reliability and limits

- Local SQLite ledger prevents repeat outreach per sender/recipient, including across restarts.
- An `uncertain` record is written before pressing Enter. A crash or error never triggers an automatic retry.
- `send_attempted_review` means a send was attempted without a detected error, NOT delivered or read. Inspect Instagram for confirmation.
- Previously recorded profiles are always skipped. This prototype has no retry/reset button; reconcile uncertain outcomes manually before any future implementation adds retries.
- The 30-second pause is ordinary pacing, not a protection against restrictions. No proxy rotation, CAPTCHA solving or challenge bypass is included.
- Login challenges, known English restriction messages, account mismatch, missing controls or uncertain recipient identity stop the whole batch. Detection cannot cover every possible Instagram error.
- Shared multi-user assignment, automatic reply detection, influencer crawling/scoring and direct Google Sheets sync are not included.
- Browser session and message logs are in `AraviOutreachData` in your home folder. Treat this folder as sensitive; never share it. The downloadable package contains no sessions or credentials.
- Closing the app during a send may leave an uncertain result. Inspect Instagram before retrying elsewhere.

## Validation

Run `python -m unittest discover -s tests -v`. These tests cover import validation, duplicates, ledger recovery and CSV formula protection. Live Instagram sending has not been tested; first run draft mode on a team-owned test profile before attempting real outreach.
