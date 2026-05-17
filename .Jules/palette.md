## 2024-05-17 - Multilingual UX & Interaction Feedback
**Learning:** In a multilingual bot, hardcoded system messages in one language create a jarring experience for users who chose a different language. Providing localized "waiting" and "error" messages significantly improves perceived quality.
**Action:** Always use a `LOCALIZED_MESSAGES` dictionary or a proper i18n system for any user-facing status messages.

**Learning:** Visual feedback during long-running async tasks (like AI response generation) is crucial. `send_chat_action(action='typing')` prevents users from thinking the bot is frozen.
**Action:** Implement `typing` action immediately after sending a "waiting" status message.

**Learning:** Replacing a "waiting" message with the final response using `edit_text` reduces chat clutter and feels more "app-like" compared to sending multiple messages.
**Action:** Store the status message object and use `edit_text` for the final delivery of the response.
