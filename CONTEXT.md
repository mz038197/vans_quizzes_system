# Vans Quizzes

Teachers open Class Sessions that offer one or more of their quiz banks; students open a Class Session through its code and take its quiz banks one by one, only inside its time window.

## Language

**Teacher**:
A person with the teacher or admin role on vans_coding_router who signed in here through the router. This system has no accounts of its own; the router decides who is a Teacher, and an admin is a Teacher like any other. Students are never Teachers and never sign in.
_Avoid_: Account, user, admin (as a separate role here)

**Quiz Bank**:
A teacher-owned collection of questions. Students reach it only through a Class Session that offers it; the Quiz Bank itself has no code. Modes are fixed (all questions) or practice (drawn subset). A Quiz Bank sits in at most one Folder. Deleting a Quiz Bank permanently removes it with its questions, Class Sessions and Submissions.
_Avoid_: Exam, test paper, quiz set

**Time Limit**:
An optional duration, in minutes, that a Class Session sets for one Quiz Bank it offers: how long one Take of that Quiz Bank may last. A Quiz Bank on its own has no Time Limit; it is only the questions. When set, it applies to both fixed and practice Takes. It is separate from the Class Session's start and end, which decide when a Take may happen at all. It can change only before the Class Session starts. When unset, the Take shows Elapsed Time counting up instead of a countdown.
_Avoid_: Exam duration, deadline, timeout (as the setting name)

**Take**:
One in-progress answering of a Quiz Bank in one Class Session, from the moment the student can answer on screen until hand-in. The Time Limit countdown starts at the beginning of a Take; continuity across refresh is kept in the student's browser only (clearing site data may start a fresh countdown). Each Take has a Take Order fixed when the Take begins.
_Avoid_: Attempt, session (for the answering period), exam sitting

**Take Order**:
The per-Take sequence of questions shown to the student — a shuffle of the fixed bank (or of the practice draw), chosen when the Take begins and unchanged until hand-in. The same order is stored on the Submission and used on the student result and the teacher's submission detail.
_Avoid_: Shuffle, random order (as the concept name), question sequence

**Review Flag**:
A student-set toggle on a question during a Take meaning “come back to this later” (e.g. hard or unsure). It does not affect scoring and is independent of whether the question already has an answer. During the Take, flags live in the student's browser with other Take continuity; flags still on at hand-in are stored on the Submission and shown on both the student result and the teacher's submission views.
_Avoid_: Bookmark, deferred, mark for grading, difficult tag (as the concept name)

**Submission**:
A student's completed set of answers for one Take of one Quiz Bank in one Class Session, including score, when it was handed in, Elapsed Time, the Take Order for that Take, and which questions still had a Review Flag at hand-in. Hand-in time is shown in UTC+8.
_Avoid_: Attempt, result record (for the persisted hand-in itself)

**Result Link**:
The unguessable link that opens one Submission's result for the student who handed it in. Anyone who holds the link can open it, so it is shared only on purpose; the Teacher opens the same result from the submissions list after signing in.
_Avoid_: Result URL with a submission number, score link

**Elapsed Time**:
How long a Take lasted from start until hand-in, stored on the Submission and shown on the student result and the teacher's submission list.
_Avoid_: Duration, time spent (as the persisted field name)

**UTC+8**:
The fixed product timezone for every wall-clock time shown to users (teachers and students), including UI and exports — Submission hand-in, Quiz Bank created day, and date-only calendar days use the UTC+8 day boundary. No timezone label is shown. Does not apply to Elapsed Time.
_Avoid_: Taiwan time, local time, browser timezone

**Time-up Hand-in**:
When the Time Limit expires or the Class Session ends, whichever comes first, the Take is submitted immediately with answers so far (blank items score as unanswered), then the student is told which one happened; confirming that message opens the result. The Submission records Elapsed Time only — not a separate “timed out” reason.
_Avoid_: Forced submit (as the user-facing name)

**Class Session**:
One run of one or more Quiz Banks for students, with a name (such as a class), a start and an end, and its own code. Students open it with its code and take each Quiz Bank it offers as a separate Take, each with its own Submission, only between the start and the end. A Quiz Bank can be offered by many Class Sessions, also at the same time, and each Class Session keeps its own Submissions. Deleting a Class Session permanently deletes its Submissions too.
_Avoid_: 教室, Classroom, session (alone), access code (as a Quiz Bank property)

**Folder**:
A teacher-owned, named place for Quiz Banks, shown as 資料夾. A Quiz Bank sits in at most one Folder; one with no Folder is shown under “未分類”, which is not a Folder. Folders do not nest. Deleting a Folder moves its Quiz Banks back to “未分類” and deletes no Quiz Bank.
_Avoid_: Group, 分組, tag, category (as the concept name)
