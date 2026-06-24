## 2026-06-24 - Interaction Snappiness via Message Editing
**Learning:** Editing a 'Waiting' status message to display the final AI response reduces chat noise and makes the bot interface feel significantly more responsive and 'snappier' compared to sending new messages for each state.
**Action:** Always prefer editing existing status messages for AI response delivery in Telegram bots to maintain a clean chat history.

## 2026-06-24 - Trilingual Accessibility for Onboarding
**Learning:** In multilingual assistants, localizing all system feedback (success confirmations, progress indicators, and error messages) is essential for maintaining trust and perceived quality for non-primary script users.
**Action:** Ensure the initial `/start` prompt is trilingual if the bot supports multiple languages, so users can navigate to their preferred language even if they don't understand the default.
