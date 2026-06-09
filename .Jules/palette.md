## 2025-05-15 - Localization and Interaction Flow
**Learning:** In multilingual Telegram bots, unlocalized system messages (like "Waiting..." or error notifications) break the immersion and can be confusing. Using chat actions like 'typing' provides immediate non-verbal feedback that the bot is working.
**Action:** Always implement a localized mapping for all system-level feedback and use 'edit_text' on status messages to keep the chat history clean.
