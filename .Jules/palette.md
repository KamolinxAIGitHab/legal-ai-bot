## 2025-05-24 - [Localized System Messages and Interaction Flow]
**Learning:** For multilingual bots, the UX begins before language selection. A tri-lingual initial prompt ensures immediate accessibility. Additionally, combining `send_chat_action('typing')` with `edit_text` on a "waiting" message provides a smooth, low-noise interaction flow that keeps the user informed without cluttering the chat history.
**Action:** Always localize system messages (errors, waiting) based on the user's selected language and use message editing for asynchronous AI responses to maintain a clean UI.
