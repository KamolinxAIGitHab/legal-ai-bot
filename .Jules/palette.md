## 2025-05-14 - [Multilingual Feedback Localization]
**Learning:** In a multilingual Telegram bot, hardcoded system feedback (waiting states, error messages) in a single language breaks the user's immersion and reduces accessibility for non-native speakers of that language. Localizing these "non-content" strings is critical for a professional UX.
**Action:** Use a centralized localization mapping and ensure all user-facing strings (including error messages and loading states) are keyed to the user's selected language.

## 2025-05-14 - [Interaction Polish with Message Editing]
**Learning:** Telegram bots that send new messages for every update (e.g., "Waiting" followed by "Answer") clutter the chat history. Editing the existing "Waiting" message with the final result provides a smoother, app-like transition.
**Action:** Use `edit_message_text` to replace placeholder states with final results, and combine with `send_chat_action('typing')` for immediate visual feedback.
