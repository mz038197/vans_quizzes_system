# A Course holds Class Sessions, and an ended Course ends them all

Status: accepted. Amends ADR 0010.

Every Class Session belongs to one Course. A Course has a name, an optional end, and is open or ended. The server checks the Course each time it checks a Class Session's window: a Take can start, and a hand-in is accepted, only while the Class Session is inside its own window **and** its Course is open with its end (if any) still ahead. Ending a Course does not change the start or end of its Class Sessions. So when the Teacher opens the Course again, each Class Session whose own end is still ahead works again. This is the same model as Class and Class Session on vans_coding_router (its ADR 0061), and the same rule for the Teacher on both systems.

## Considered Options

- **Set every Class Session's end to now when the Course ends**: rejected. Opening the Course again would then need the Teacher to fix each Class Session's end, and the original times would be lost.
- **No Course; one Class Session stands alone (ADR 0010 as written)**: rejected. A Teacher runs many lessons for one class over a term and wants to close them all at once and see one grade sheet for the term.
- **Only an admin can open an ended Course again, as on the router**: rejected. This system has no admin role apart from Teachers (ADR 0007).

## Consequences

- An ended Course takes no new Class Session. A Class Session end later than the Course end can be saved, but it stops at the Course end.
- Deleting a Course deletes its Class Sessions and their Submissions, after a confirmation that names how many will go and asks for the Course name.
- The migration makes one ended Course 「改版前」 for each Teacher with old Submissions. In it, each Quiz Bank with Submissions gets one ended Class Session 「改版前的作答」, and that Quiz Bank's old Submissions go there.
