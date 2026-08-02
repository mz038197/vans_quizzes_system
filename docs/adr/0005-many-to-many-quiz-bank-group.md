# Quiz Bank ↔ Group is many-to-many

A Quiz Bank can belong to many Groups (e.g. “110-1 段考” *and* “國三總複習”) and a Group can contain many Quiz Banks, so the relationship is a many-to-many join table, not a single `group_id` foreign key on `QuizBank`. Groups live in their own `QuizBankGroup` table; a Quiz Bank with no links is shown under the virtual “未分組” entry on the dashboard and is not stored as a Group.

**Considered options:** single `category` string on `QuizBank` (simple, but blocks a Quiz Bank from being in two collections at once and scatters category names across rows); a single `group_id` foreign key (clean schema, same one-bucket problem). Rejected for the many-to-many shape so a teacher can re-bucket the same Quiz Bank without duplicating it.
