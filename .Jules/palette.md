## 2025-05-14 - [Centralized Localization and Dynamic Status Updates]
**Learning:** Using a `LOCALIZED_MESSAGES` dictionary ensures consistency across all supported languages (Cyrillic Uzbek, Latin Uzbek, Russian) for system notifications. Combining `send_chat_action('typing')` with `edit_text` for the status message creates a smoother transition from "waiting" to "result" and reduces chat clutter.
**Action:** Always implement a localized message map and use message editing for long-running AI responses to maintain a clean and responsive UI.
