## 2025-05-22 - [Localized UX & Clutter Reduction]
**Learning:** Telegram bots feel more responsive when they use `send_chat_action('typing')` immediately and edit status messages instead of sending new ones. Providing localization for "Waiting" and "Error" states is crucial for a consistent multilingual experience.
**Action:** Always implement a localized messages dictionary and use `edit_text` for async AI responses to keep the chat history clean.
