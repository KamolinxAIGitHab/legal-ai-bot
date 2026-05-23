## 2024-05-23 - [UX Improvement: Feedback and Clarity]
**Learning:** Combining `context.bot.send_chat_action(action='typing')` with `edit_text` provides immediate visual feedback while reducing chat clutter, creating a smoother user experience during long-running async operations like AI text generation.
**Action:** Always use `typing` indicators for async responses and consider editing "waiting" messages instead of sending new ones to keep the conversation concise.
