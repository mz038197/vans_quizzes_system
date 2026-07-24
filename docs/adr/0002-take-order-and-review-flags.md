# Take Order and Review Flags on Submission

Every Take shuffles into a frozen Take Order (fixed banks and practice draws). Review Flags are a student-only “come back later” toggle during the Take: mid-Take they stay in the browser with other Take continuity; at hand-in, still-active flags and the Take Order are stored on the Submission. Student results and teacher submission detail both show that Take Order and those flags so numbering matches what the student saw.

**Considered options:** mid-Take server sync for flags (rejected — students are name-only; keep continuity client-side like ADR-0001); drop flags at hand-in (rejected — teachers and students need the “unsure” signal on the result); show results in bank `order_index` (rejected — breaks alignment with flagged question numbers).
