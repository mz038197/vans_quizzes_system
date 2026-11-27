# A Quiz Bank sits in at most one Folder

Status: accepted. Supersedes ADR 0005.

ADR 0005 planned many-to-many Groups, and that design was never built. The Teacher wants to drag a Quiz Bank into a Folder and to see a Folder's Quiz Banks only after opening it. A drag only means "move" when a Quiz Bank lives in one place, so each Quiz Bank has at most one Folder (a nullable folder reference on the Quiz Bank). Folders do not nest. Deleting a Folder moves its Quiz Banks back to "未分類".

## Considered Options

- **Many-to-many Groups (ADR 0005)**: rejected. With a Quiz Bank in several Groups, a drag is unclear (move or copy?), and opening a Group no longer shows "where the Quiz Bank is".
- **Nested Folders**: rejected for now. One level is enough to sort one Teacher's Quiz Banks; nesting adds breadcrumbs and drag rules that nobody asked for.
