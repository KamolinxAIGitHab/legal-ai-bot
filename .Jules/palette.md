## 2025-05-15 - Multi-language UX Patterns in Telegram Bots
**Learning:** In multi-lingual bots, failing to localize non-core system feedback (like 'Waiting' or error messages) creates a jarring experience. Always ensure system feedback matches the user's selected language.
**Action:** Use a compact dictionary mapping for localization and store the result of 'waiting' messages to use `edit_text` for final responses, keeping the chat interface clean.
