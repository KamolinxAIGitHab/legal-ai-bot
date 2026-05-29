## 2025-05-14 - System Message Localization and Interaction Flow
**Learning:** In multi-lingual Telegram bots, failing to localize non-core system feedback (like 'Waiting' or error messages) creates a jarring experience; always ensure these match the user's selected language. Additionally, using `edit_message_text` to replace loading states with results reduces chat history clutter and improves perceived speed.
**Action:** Always implement a centralized localization mapping for system strings and use message editing for transition states.
