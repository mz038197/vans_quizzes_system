# Hard-delete Quiz Bank with Submissions

## Summary

Teachers can hard-delete a Quiz Bank that already has Submissions; deletion permanently removes the bank, its questions, and all Submissions. Deactivation remains separate.

## Requirements

1. `DELETE /api/quiz-bank/<id>` with no Submissions succeeds and removes the Quiz Bank (and questions).
2. `DELETE /api/quiz-bank/<id>` with Submissions and without `confirm: true` is rejected (e.g. 409) and returns the Submission count.
3. `DELETE /api/quiz-bank/<id>` with Submissions and `confirm: true` succeeds; those Submissions are gone.
4. Non-owner still gets 403.
5. Teacher UI warns with Submission count when needed and sends `confirm: true` on confirmed delete.
6. Access codes become reusable after delete; mid-Take does not block delete.
