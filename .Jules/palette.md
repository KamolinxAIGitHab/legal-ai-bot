## 2026-05-26 - [Full Localization & Clean Interactions]
**Learning:** For multi-lingual bots, it is crucial to localize all system-generated strings (waiting status, errors, disclaimers) to match the user's selected language. Combining this with visual progress (typing indicators) and in-place editing (using `edit_text`) creates a professional and accessible "app-like" experience within Telegram.
**Action:** Always maintain a localization mapping for all system messages and prioritize in-place updates over sending new messages for state changes.
