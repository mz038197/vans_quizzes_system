# Vans Quizzes

Teachers publish quiz banks that students take via a shareable access code; timed and untimed attempts are both first-class.

## Language

**Quiz Bank**:
A teacher-owned collection of questions that students open with an access code. Modes are fixed (all questions) or practice (drawn subset).
_Avoid_: Exam, test paper, quiz set

**Time Limit**:
An optional duration, in minutes, on a Quiz Bank. When set, it applies to both fixed and practice takes; when unset, the take has no countdown and no auto-submit.
_Avoid_: Exam duration, deadline, timeout (as the bank setting name)

**Take**:
One in-progress answering of a Quiz Bank, from the moment the student can answer on screen until hand-in. The Time Limit countdown starts at the beginning of a Take; continuity across refresh is kept in the student's browser only (clearing site data may start a fresh countdown).
_Avoid_: Attempt, session (for the answering period), exam sitting

**Submission**:
A student's completed set of answers for one Take of a Quiz Bank, including score, when it was handed in, and Elapsed Time when the Quiz Bank had a Time Limit.
_Avoid_: Attempt, result record (for the persisted hand-in itself)

**Elapsed Time**:
How long a Take lasted from start until hand-in, stored on the Submission and shown on the student result and the teacher's submission list.
_Avoid_: Duration, time spent (as the persisted field name)

**Time-up Hand-in**:
When the Time Limit expires, the Take is submitted immediately with answers so far (blank items score as unanswered), then the student is told time is up; confirming that message opens the result. The Submission records Elapsed Time only — not a separate “timed out” reason.
_Avoid_: Forced submit (as the user-facing name)
