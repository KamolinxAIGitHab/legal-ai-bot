## 2026-06-25 - Telegram Bot Visual Feedback
**Learning:** Localizing system feedback (waiting, errors, disclaimers) is essential for a consistent trilingual experience; additionally, editing existing status messages instead of sending new ones significantly reduces chat noise and makes the bot feel more responsive.
**Action:** Always implement message editing for status updates in Telegram bots and ensure every user-facing string is mapped to the selected language early in the handler scope.
