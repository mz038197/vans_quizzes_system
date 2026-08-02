# Group feature does not include a full Quiz Bank editor

The Group feature ships with two assignment surfaces only: a multi-select on the *create* form, and a “管理群組” modal on each dashboard card that just edits Group membership. It deliberately does **not** add a general “edit Quiz Bank” page (title / description / Time Limit / scoring mode / …). Editing those fields continues to live wherever it lived before this feature — adding it as part of Group work would quietly double the scope and entangle the new schema with unrelated fields.

**Considered options:** ship the editor at the same time (tempting because the create form already shows the same fields, so “just reuse it for edit” feels cheap). Rejected — a separate editor is its own design decision (URL, partial-save, validation reuse) and deserves its own ADR when it actually happens.
