# A student's result opens by an unguessable Result Link

Status: accepted.

The student result used to open at `/result/<submission id>`. That id is a counter, and the page needs no sign-in and shows every correct answer, so anyone could read other students' results and the answer key. Each Submission now has a random `result_token`, and the student result opens only at `/result/<result_token>`. A Teacher opens one Submission from the submissions list at a separate address that needs sign-in and checks that the Teacher owns the Quiz Bank.

A one-time startup migration gave every old Submission a token; production ran it on 2026-11-27, and its code was then removed. Old `/result/<number>` links that students saved stop working; a Teacher still sees every old Submission.

## Considered Options

- **Keep numeric ids and add a check**: rejected. Students do not sign in, so there is no one to check.
- **Hide correct answers on the result page**: not part of this decision. A student can still share their own Result Link, which shows the correct answers. A per-bank setting for that is separate work.
