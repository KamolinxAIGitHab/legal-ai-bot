## 2025-05-14 - Localized UX Feedback and Message Editing

**Learning:** In multi-lingual Telegram bots, failing to localize non-core system feedback (like 'Waiting' or error messages) creates a jarring experience. Additionally, editing existing messages instead of sending new ones reduces chat clutter and feels more like a modern application interaction.

**Action:** Always provide localized feedback for all system states (loading, success, error) and prefer `edit_text` over `send_text` for status updates to maintain a clean chat history.
