# Vans Quizzes

Teachers publish quiz banks that students take via a shareable access code; timed and untimed attempts are both first-class.

## Language

**Quiz Bank**:
A teacher-owned collection of questions that students open with an access code. Modes are fixed (all questions) or practice (drawn subset). Deleting a Quiz Bank permanently removes it with its questions and Submissions; deactivating leaves Submissions intact. After deletion its access code may be reused.
_Avoid_: Exam, test paper, quiz set

**Time Limit**:
An optional duration, in minutes, on a Quiz Bank. When set, it applies to both fixed and practice takes; when unset, the take has no countdown and no auto-submit.
_Avoid_: Exam duration, deadline, timeout (as the bank setting name)

**Take**:
One in-progress answering of a Quiz Bank, from the moment the student can answer on screen until hand-in. The Time Limit countdown starts at the beginning of a Take; continuity across refresh is kept in the student's browser only (clearing site data may start a fresh countdown). Each Take has a Take Order fixed when the Take begins.
_Avoid_: Attempt, session (for the answering period), exam sitting

**Take Order**:
The per-Take sequence of questions shown to the student — a shuffle of the fixed bank (or of the practice draw), chosen when the Take begins and unchanged until hand-in. The same order is stored on the Submission and used on the student result and the teacher's submission detail.
_Avoid_: Shuffle, random order (as the concept name), question sequence

**Review Flag**:
A student-set toggle on a question during a Take meaning “come back to this later” (e.g. hard or unsure). It does not affect scoring and is independent of whether the question already has an answer. During the Take, flags live in the student's browser with other Take continuity; flags still on at hand-in are stored on the Submission and shown on both the student result and the teacher's submission views.
_Avoid_: Bookmark, deferred, mark for grading, difficult tag (as the concept name)

**Submission**:
A student's completed set of answers for one Take of a Quiz Bank, including score, when it was handed in, Elapsed Time when the Quiz Bank had a Time Limit, the Take Order for that Take, and which questions still had a Review Flag at hand-in. Hand-in time is shown in UTC+8.
_Avoid_: Attempt, result record (for the persisted hand-in itself)

**Elapsed Time**:
How long a Take lasted from start until hand-in, stored on the Submission and shown on the student result and the teacher's submission list.
_Avoid_: Duration, time spent (as the persisted field name)

**UTC+8**:
The fixed product timezone for every wall-clock time shown to users (teachers and students), including UI and exports — Submission hand-in, Quiz Bank created day, and date-only calendar days use the UTC+8 day boundary. No timezone label is shown. Does not apply to Elapsed Time.
_Avoid_: Taiwan time, local time, browser timezone

**Time-up Hand-in**:
When the Time Limit expires, the Take is submitted immediately with answers so far (blank items score as unanswered), then the student is told time is up; confirming that message opens the result. The Submission records Elapsed Time only — not a separate “timed out” reason.
_Avoid_: Forced submit (as the user-facing name)
