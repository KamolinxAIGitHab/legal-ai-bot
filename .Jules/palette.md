## 2025-05-15 - [Telegram Bot UX Patterns]
**Learning:** For multilingual Telegram bots, a cohesive UX requires localizing all system feedback (waiting states, success confirmations, and error messages) to avoid jarring language switches. Using chat actions ('typing') provides immediate affordance for long-running AI tasks, while editing status messages instead of sending new ones significantly reduces chat history clutter and keeps the interaction focused.
**Action:** Always implement a localized message mapping and utilize message editing for state transitions in Telegram bot interfaces.
