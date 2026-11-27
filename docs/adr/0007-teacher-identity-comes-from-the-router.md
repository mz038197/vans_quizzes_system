# Teacher identity comes from the router; this system keeps no accounts

Status: accepted.

Teachers sign in through vans_coding_router with the `openid teacher` scope (router ADR 0094): Google only, and only for a holder of the teacher or admin role. The router returns an ID token with the router user id and Display Name, and this system keeps both in a signed cookie for 12 hours. It does not ask the router again during those 12 hours. `QuizBank.teacher_id` holds the router user id. The `user` table, passwords, emails, `/register`, and `/login` are gone. Students do not sign in: they still open a Quiz Bank by its access code and type their own name.

An admin is a Teacher like any other and sees only the Quiz Banks they own. This system needs no Service Credential, because it never asks the router which Classes a Teacher manages.

## Considered Options

- **Keep the `user` table and add a `router_user_id` column**: rejected. It keeps a second copy of the Teacher that can go stale, and it keeps email and password columns that nothing uses.
- **Rename `teacher_id` to `owner_id`**: rejected. `teacher_id` already names the Teacher, and the rename touches every ownership check for no gain.
- **Re-check the Teacher's role with the router on every request, as club-booking-board does**: rejected. That needs a Service Credential and the Teacher Classes call. A Teacher who loses the role keeps access for at most 12 hours, and that is acceptable here.
- **Keep password login next to router login for a while**: rejected. There is one Teacher, and the move is done in one deploy after a database backup.

## Consequences

- To give another person access, give that person the teacher role on the router.
- A one-time startup move gave every Quiz Bank to the router user id in `QUIZZES_OWNER_ROUTER_USER_ID` and dropped the `user` table. Production ran it on 2026-11-27, and its code was then removed. A database from before PR #1 must run that move and the `result_token` backfill (ADR 0008) from git history first.
- A `SECRET_KEY` that is missing, left at the default, or shorter than 32 characters stops the app from starting in production, because that key signs the Teacher cookie.
- Teacher writes are refused unless `Origin` is this site's own origin. `SameSite=Lax` alone does not stop a request from another `*.vanscoding.com` site.
