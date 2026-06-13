## 2025-05-15 - Improving Telegram Bot Interaction with Message Editing
**Learning:** In Telegram bots, sending new messages for every state change (e.g., "Processing...", "Done!") creates unnecessary clutter and notifications for the user. Editing an existing "status" message provides a much smoother and more professional experience.
**Action:** Always store the message object returned by the initial status message and use `edit_text` to update it with the final result or error.
