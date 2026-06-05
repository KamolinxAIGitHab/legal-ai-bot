## 2026-06-05 - [Localization & Feedback]
**Learning:** Multilingual bots feel broken if system messages (waiting, errors, start prompts) aren't localized. Users also appreciate visual feedback like "typing" states to know the AI is working. Replacing "waiting" messages with final answers via "edit_text" reduces chat clutter and provides a smoother interaction flow.
**Action:** Always localize system-level strings and use chat actions for long-running AI tasks. Prioritize editing existing messages over sending new ones for status updates.
