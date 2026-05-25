## 2025-05-15 - [Telegram Bot Interaction Flow]
**Learning:** Combining `context.bot.send_chat_action(action='typing')` with `edit_text` on a "Waiting" message provides immediate visual feedback while significantly reducing chat clutter and "notification fatigue" for users during long-running async operations.
**Action:** Always use `send_chat_action` immediately after a trigger, and prefer `edit_text` for updating status messages to their final state.

## 2025-05-15 - [Multilingual Onboarding]
**Learning:** For bots supporting multiple languages, the initial `/start` prompt MUST be trilingual (or include all supported languages) to ensure the user can immediately identify how to proceed, regardless of their native tongue.
**Action:** Implement trilingual prompts for all critical entry points where language has not yet been established.
