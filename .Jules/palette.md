## 2026-05-16 - [Localized Status Messages & Typing Indicator]
**Learning:** In a multilingual bot, hardcoded system messages in one language break the immersion for users of other languages. Immediate feedback via typing indicators and reducing chat clutter by editing "Waiting" messages significantly improves perceived performance and UX.
**Action:** Always use a localized message dictionary and prefer `edit_message_text` over multiple reply messages for status updates. Ensure typing indicators are sent AFTER the status message to persist during async operations.
