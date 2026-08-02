Status: ready-for-agent
Slug: groups-for-quiz-banks

# Spec: Group Quiz Banks

## Problem Statement

A teacher who has been using Vans Quizzes for a while ends up with a long, unfiltered list of Quiz Banks on the dashboard. There is no way to slice the list by topic, term, class, or any other mental bucket, and no way to sort the cards. When a teacher is preparing a class and wants to find "all the banks for 110-1 midterm" or "all the banks tagged for review before next week", they have to eyeball every card. The lack of grouping and sorting makes the dashboard unusable once a teacher has more than a handful of banks, and there is no plan B short of re-titling every bank by hand.

## Solution

Add teacher-owned **Groups** to the dashboard. A teacher can create named Groups, put any Quiz Bank into as many Groups as they want from the create form or from a "管理群組" modal on each dashboard card, and view the dashboard with a left sidebar that lists every Group (plus a virtual "未分組" entry for un-banked Quiz Banks and a virtual "全部" entry that shows everything). Clicking a sidebar entry filters the right-side card grid to just that Group. Above the card grid there is a sort control with two options: by 編輯時間 (newest edit first) and by 名稱 (A→Z). Group names are teacher-scoped, Groups persist independently of Quiz Banks, and deleting a Group never deletes a Quiz Bank — it only removes the link and the Quiz Bank falls back to "未分組".

## User Stories

1. As a teacher, I want to create a named Group on the dashboard, so that I can start organising my Quiz Banks.
2. As a teacher, I want to rename a Group, so that I can correct typos or relabel a collection without rebuilding it.
3. As a teacher, I want to delete a Group, so that I can remove collections I no longer need.
4. As a teacher, I want a Quiz Bank to belong to zero, one, or many Groups at the same time, so that the same bank can sit in "110-1 段考" and "國三總複習" without duplicating it.
5. As a teacher, I want to pick one or more Groups when creating a new Quiz Bank, so that the bank is correctly filed from day one.
6. As a teacher, I want to change a Quiz Bank's Group membership from the dashboard (without opening a full edit page), so that re-filing a bank is one click.
7. As a teacher, I want a sidebar on the dashboard that lists every Group, so that switching between Group views is one click.
8. As a teacher, I want the sidebar to show the count of Quiz Banks in each Group, so that I can tell at a glance which Group is biggest.
9. As a teacher, I want a "全部" entry in the sidebar that shows every Quiz Bank I own, so that I can drop out of grouping and see the full list.
10. As a teacher, I want a "未分組" entry in the sidebar that shows Quiz Banks not in any Group, so that I can find banks I haven't filed yet.
11. As a teacher, I want the empty Group to still appear in the sidebar (with a (0) count), so that I don't lose track of a Group I've just emptied.
12. As a teacher, I want a sort control above the card grid that lets me sort by 編輯時間 (most recently edited first) or by 名稱 (A→Z), so that I can find banks faster.
13. As a teacher, I want the sort choice to persist while I switch between sidebar entries, so that I don't have to re-pick it every time.
14. As a teacher, I want only my own Groups and Quiz Banks to appear in the sidebar and grid, so that another teacher's data never leaks into my view.
15. As a teacher, I want the sidebar to be available on desktop and degrade to a horizontal chip row on small screens, so that grouping still works on a phone.
16. As a teacher, I want the sidebar's "全部 / 未分組 / each Group" selection to drive which card grid I see, so that the dashboard is one consistent view, not two pages.
17. As a teacher, I want creating, renaming, and deleting a Group to require confirmation where destructive, so that I don't lose a collection by accident.
18. As a teacher, I want Group management to leave Quiz Bank data alone (questions, submissions, time limit, scoring mode all untouched), so that grouping is a non-destructive layer.
19. As a teacher, I want a Group to be deletable even if it currently contains Quiz Banks, so that I'm not blocked by "empty the group first" friction — the banks just fall back to "未分組".
20. As a teacher, I want renaming a Group to update every place it appears (sidebar, card tags, etc.) immediately, so that the dashboard stays self-consistent.
21. As a teacher, I want the dashboard's existing actions (manage questions, view submissions, copy link, toggle active, delete bank) to keep working unchanged when a Group is selected, so that grouping is purely additive.
22. As a teacher, I want the "管理群組" modal on a card to show which Groups the bank is currently in, so that I can make an informed choice.
23. As a teacher, I want a Quiz Bank that already has Submissions to be filable into Groups like any other, so that history and grouping are independent.
24. As a teacher, I want the 編輯時間 sort to reflect real edits to the bank (title, description, questions, time limit, scoring mode, group membership), so that the sort is meaningful, not just a creation timestamp.
25. As a teacher, I want the sort order to be stable within the same key, so that two banks with the same name or same edit time don't shuffle on every reload.
26. As a developer, I want the new updated_at column on QuizBank to be set explicitly on every code path that mutates a bank, so that the sort stays honest even on paths SQLAlchemy's onupdate might miss.

## Implementation Decisions

- **Domain vocabulary**: the new first-class concept is Group, added to CONTEXT.md alongside the existing Quiz Bank glossary entry. The sidebar entry "未分組" is not a stored Group; it is a UI concept meaning "this Quiz Bank has no Group links."
- **Data model**:
  - New table QuizBankGroup (id, teacher_id FK to User, name, created_at).
  - Many-to-many between QuizBank and QuizBankGroup via a join table (SQLAlchemy secondary).
  - QuizBank gains an updated_at column (DateTime, nullable). Every code path that mutates a QuizBank must set updated_at = datetime.utcnow() explicitly — do not rely on SQLAlchemy onupdate alone, because some edits (e.g. only touching a relationship) do not trip it.
  - All existing QuizBank columns and relations stay as they are; no migration of legacy data is needed beyond adding the new column and the new tables.
- **HTTP API surface** (the only seam — see Testing Decisions):
  - POST /api/groups — create a Group for the current teacher. Body: {name}. Returns the new Group (id + name).
  - PATCH /api/groups/<id> — rename a Group. Body: {name}. 404 if not owned by current teacher.
  - DELETE /api/groups/<id> — delete a Group. Idempotent for links (links are removed by the join-table cascade; the QuizBanks themselves are untouched and fall back to "未分組").
  - POST /api/quiz-bank/<id>/groups — set the full Group-membership list for a Quiz Bank. Body: {group_ids: [...]}. Replaces the previous set (PUT-style semantics on a POST endpoint, matching the rest of this codebase's pragmatic style). 404 if the Quiz Bank is not owned by current teacher; 400 if any group_id is not owned by the same teacher.
  - GET /teacher-dashboard — gains query params ?group=<id|all|ungrouped> and ?sort=<updated_desc|name_asc>; returns the filtered + sorted card grid plus the sidebar list (with per-Group counts). Existing query-string absence means "全部, by 編輯時間."
  - POST /create-quiz-bank — body gains optional group_ids: [...]; behaviour is identical when the field is absent or empty (back-compat).
- **Template / UI**:
  - teacher_dashboard.html becomes a two-column layout: left sidebar listing Groups + "全部" + "未分組", each with a (N) count; right side keeps the existing card grid and gains a small sort control above it.
  - On small screens the sidebar collapses to a horizontal chip row at the top of the card grid (same data, different presentation).
  - Each card gains a "管理群組" button that opens a modal listing every Group the teacher owns, with checkboxes pre-set to the bank's current membership, and a single "儲存" that POSTs the full membership set.
  - create_quiz_bank.html gains a multi-select for Groups in its existing form; the field is optional.
- **Authorisation**: every new route scopes to current_user.id. A teacher cannot read, rename, delete, or assign another teacher's Groups, and cannot change Group membership of another teacher's Quiz Bank.
- **Schema-migration strategy**: extend whatever the project already uses (no precedent for Alembic in the repo, so a hand-written ALTER TABLE / CREATE TABLE step inside the existing ensure_schema_updates() helper is acceptable; the helper already exists in app.py).
- **Empty-state rules**:
  - A Group with zero Quiz Banks is still listed in the sidebar (with (0)).
  - A teacher with zero Groups sees only "全部 / 未分組" in the sidebar; the "管理群組" modal on each card then doubles as a way to create a Group inline if the list is empty.
- **Sort stability**: when the sort key is equal, fall back to id ASC so that order is deterministic across reloads.
- **Glossary & ADRs**: vocabulary change is in CONTEXT.md (already landed during grilling); the two architectural decisions live in docs/adr/0005-many-to-many-quiz-bank-group.md and docs/adr/0006-group-feature-stays-narrow.md (already landed).

## Testing Decisions

- **Seam**: a single HTTP seam. Tests drive the Flask test client against the routes listed under Implementation Decisions, and assert on response status, JSON body, and the resulting database state via the same app.app_context() pattern that tests/test_delete_quiz_bank.py already uses. No new test seam (no separate groups_utils module, no model-level test layer) is introduced — the codebase's six existing test files all follow this style, and adding a second seam here would be the only place in the repo that has one.
- **What makes a good test**: assert the external contract the route promises, not how it implements it. So "a deleted Group leaves its banks queryable as ungrouped" is in; "the join table has no row for that pair" is out. HTML assertions stay high-level: the response contains the Group name, the count, or the right card; no CSS selectors, no Jinja internals.
- **What gets covered**:
  - Group CRUD: create, rename (own / not-own), delete (with banks / without banks), ownership 404.
  - Membership: assign at create time, change from card modal, replace (not merge) semantics, ownership mismatch 400.
  - Dashboard filter: ?group=<id>, ?group=ungrouped, ?group=all, default behaviour, only current teacher's banks appear, only current teacher's Groups appear in sidebar.
  - Sidebar counts: per-Group count, "未分組" count, "全部" count, empty Group appears as (0).
  - Sort: ?sort=updated_desc (most recently edited first), ?sort=name_asc, default when absent, deterministic tie-break.
  - updated_at honesty: every route that mutates a Quiz Bank (create, groups membership change, and any pre-existing edit path the agent touches) leaves updated_at strictly greater than the previous value.
  - Non-regression: existing dashboard cards still expose manage-questions / view-submissions / copy-link / toggle / delete actions when a Group filter is active.
- **Prior art**: tests/test_delete_quiz_bank.py (HTTP seam + app.app_context() DB inspection + auth_client fixture) and tests/conftest.py (the auth_client fixture that pre-seeds a teacher, a bank, and a question) are the templates. The new test_groups_for_quiz_banks.py reuses both; if a test needs a second Quiz Bank or a Group, it creates one inside the test (mirroring how test_delete_quiz_bank.py adds Submissions inline).

## Out of Scope

- A general "edit Quiz Bank" page (title / description / Time Limit / scoring mode / …). ADR 0006 records this as a deliberate non-goal; it can be picked up as its own spec later.
- Drag-and-drop re-grouping in the sidebar. Card-level "管理群組" modal is enough for v1.
- Group colours, icons, ordering, or any per-Group presentation beyond the name and the count.
- Cross-teacher Groups, sharing Groups between teachers, or any read-only "view another teacher's Group" affordance.
- Student-facing surfaces. Groups live entirely on the teacher dashboard; the student entry point (/quiz/<access_code>) is unchanged.
- Bulk operations ("move all selected banks into this Group"). v1 is one bank at a time via the modal.
- Reordering banks inside a Group by drag. Sorting is by 編輯時間 or 名稱 only.

## Further Notes

- The updated_at discipline is the one place this spec is opinionated about implementation: it must be set explicitly on every mutation path, because some mutations (relationship-only changes) won't trip SQLAlchemy's onupdate. The updated_at honesty test in Testing Decisions is what enforces this in CI, not a code review.
- The "未分組" virtual entry is a query, not a row. The dashboard route computes the count of Quiz Banks for the current teacher whose groups collection is empty and exposes it as the "未分組" sidebar entry. It is deliberately not a sentinel Group in the database, so renaming or deleting "未分組" is impossible by construction.
- Deleting a Group is a single DELETE against the join rows (cascade) plus a DELETE of the Group row. The QuizBanks are not touched. The agent should not add a "move banks out first" step.