## 2025-05-15 - [Multilingual UX Consistency]
**Learning:** Hardcoded system messages (waiting indicators, error messages, disclaimers) in a single language create a jarring experience in multilingual bots once a user has selected their preferred language.
**Action:** Always use a localization mapping (e.g., `LOCALIZED_MESSAGES`) for all system-side feedback to ensure the entire interaction remains in the user's chosen language.

## 2025-05-15 - [Reducing Chat Clutter]
**Learning:** Sending a "waiting" message followed by a separate "response" message increases chat noise and requires the user to scroll more.
**Action:** Store the "waiting" message object and use `.edit_text()` to replace it with the final AI response or error message for a smoother, cleaner interaction.
