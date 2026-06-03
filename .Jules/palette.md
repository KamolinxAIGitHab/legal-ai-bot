## 2026-06-03 - [Stateful UI Updates & Immediate Feedback]
**Learning:** Using message editing (`edit_text`) to transition from a "waiting" status to the final AI response significantly reduces chat clutter. Combining this with immediate visual feedback via `send_chat_action('typing')` makes the bot feel more responsive and professional. It is critical to also handle errors by editing the same message to prevent "ghost" waiting indicators.
**Action:** Implement stateful message transitions and immediate visual feedback for all long-running AI operations.
