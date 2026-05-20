## 2025-05-20 - Multi-step Feedback and Localized UX
**Learning:** In multilingual bots, hardcoded status messages (like "Waiting...") disrupt the immersion. Providing immediate visual feedback via `send_chat_action('typing')` combined with editing the status message instead of sending new ones significantly improves perceived responsiveness and reduces chat clutter.
**Action:** Always localize system messages (wait, error, disclaimer) and use message editing for async operations to maintain a clean conversation flow.
