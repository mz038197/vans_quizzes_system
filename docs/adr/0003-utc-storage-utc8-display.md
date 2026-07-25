# Persist wall-clock times in UTC; render as UTC+8

All human-facing wall-clock times must appear in UTC+8 (no timezone label, including date-only day boundaries). We keep persisting those instants in UTC (as with existing `utcnow` rows) and convert only when formatting for UI or export, so storage stays a single unambiguous instant and historical data needs no reinterpretation.

**Considered options:** store UTC+8 in the database — rejected to avoid dual conventions and rewriting or reinterpreting existing timestamps.
