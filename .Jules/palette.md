## 2026-05-28 - Localized Feedback & Chat Optimization
**Learning:** In multi-lingual bots, keeping system feedback (waiting states, errors) in the user's selected language is crucial for a seamless experience. Additionally, using message editing instead of new bubbles for loading states significantly reduces chat clutter and makes the interaction feel more like a modern app.
**Action:** Always localize wait/error messages and use `edit_text` to replace temporary status messages with final results.
