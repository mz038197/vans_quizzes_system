# A Class Session decides when and how long; the server checks the when

Status: accepted. Amends ADR 0001 and ADR 0004.

Students reach a Quiz Bank only through a Class Session, which has a start, an end, its own code, and an optional Time Limit for each Quiz Bank it offers. One Class Session can offer several Quiz Banks, and students take each one separately, with its own Submission. The Quiz Bank keeps only its questions, mode and scoring; it has no code, no Time Limit and no on/off switch (`is_active` is removed, so ADR 0004's "deactivation" becomes "end the Class Session"). The server refuses to start a Take outside the Class Session's start and end, and refuses a hand-in that arrives more than 1 minute after the end. The Time Limit stays in the student's browser as ADR 0001 decided.

## Considered Options

- **A time window on the Quiz Bank**: rejected. One Quiz Bank is used by many classes at different times, and each class needs its own link and its own grades.
- **Check the window only in the browser, like the Time Limit**: rejected. A student could change the computer clock and answer after the Class Session ended. The window is the rule the Teacher announces to a class, so the server must hold it; the Time Limit is per Take and the trade-off in ADR 0001 still holds.
- **Merge a Class Session's Quiz Banks into one test**: rejected. Each Quiz Bank has its own mode, draw ratios and scoring, which do not combine; to merge questions, the Teacher makes a new Quiz Bank.
- **Time Limit on the Quiz Bank**: rejected. A Quiz Bank is only the questions; how long students get depends on the class and the lesson.

## Consequences

- Every Submission belongs to one Class Session. Deleting a Class Session deletes its Submissions, after a confirmation that names how many will go.
- Old Quiz Bank access codes stop working. Nothing was in use when this changed.
