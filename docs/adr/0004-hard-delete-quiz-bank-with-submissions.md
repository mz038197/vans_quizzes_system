# Hard-delete Quiz Bank including Submissions

Teachers may permanently delete a Quiz Bank even when Submissions exist; deletion removes the bank, its questions, and all of its Submissions with no recycle bin. Soft-delete / archive was rejected because the requested outcome is irreversible cleanup, not hide-and-keep. Deactivation (`is_active`) remains the non-destructive way to stop new Takes while keeping Submissions.

When any Submission exists, the delete API requires an explicit confirm flag so a bare DELETE cannot wipe grades; zero-Submission banks delete without that flag. In-progress Takes stay client-side only (ADR-0001), so a mid-Take delete is allowed and a later hand-in may fail.
