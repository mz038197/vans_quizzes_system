# Client-side Time Limit enforcement

Status: amended by ADR 0010. The Time Limit now belongs to a Class Session and stays client-side; the Class Session's start and end are checked on the server. Elapsed Time is stored on every Submission.

Students are not logged in (name only), and we accepted that clearing browser data may reset a countdown. We keep Take start time and the countdown in the student's browser, and persist only Elapsed Time on the Submission at hand-in — not a server-side Take start or deadline check.

**Considered options:** server-recorded Take start with submit-time enforcement (stronger continuity and less easy to reset); rejected for this pass in favor of simpler client-only timing.
