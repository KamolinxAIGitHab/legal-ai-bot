## 2025-05-18 - Localized Feedback & UI Clutter Reduction
**Learning:** In multilingual Telegram bots, hardcoded system messages (waiting, error) break the user's immersion if they don't match the selected language. Additionally, sending new messages for every update creates unnecessary clutter compared to editing existing status messages.
**Action:** Always use a localization dictionary for all system strings and prefer `edit_text` to update the "Waiting..." status with the final AI response.
