## 2025-06-08 - Localized System Feedback
**Learning:** In multi-lingual Telegram bots, failing to localize non-core system feedback (like 'Waiting' or error messages) creates a jarring experience; always ensure these match the user's selected language.
**Action:** Implement localized message mappings for all system feedback (status messages, disclaimers, errors) to maintain immersion.

## 2025-06-08 - surgical diffs and line endings
**Learning:** Large block replacements can easily exceed the Palette agent's 50-line limit if line endings (CRLF vs LF) are inconsistent between the environment and the file.
**Action:** Always normalize line endings to LF using `sed -i 's/\r//' file.py` before applying surgical updates to ensure clean and compact diffs.
