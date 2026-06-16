## 2024-05-24 - Multilingual UX and Interaction Polishing
**Learning:** Localizing system feedback (waiting, errors, disclaimers) is crucial for trust in multilingual bots. Transitioning from sending new messages to editing a status message significantly improves the "snappiness" and cleanliness of the interface.
**Action:** Always centralize UI strings in a `LOCALIZED_MESSAGES` dictionary and use `edit_text` for status updates to reduce chat clutter.
