# 02 — 教師可建立、重新命名、刪除自己的 Group

**What to build:** 教師在 dashboard 能建立具名 Group、重新命名、刪除（破壞性操作需確認）。刪除 Group 只移除與 Quiz Bank 的連結，Quiz Bank 本身（題目、Submission、時限、計分等）完全不動，銀行會落到「未分組」。教師只能動自己的 Group。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 新表 QuizBankGroup（教師擁有）與 Quiz Bank ↔ Group 多對多 join；「未分組」不是資料庫列
- [ ] `POST /api/groups` 建立；`PATCH /api/groups/<id>` 改名；`DELETE /api/groups/<id>` 刪除（含有 bank 時也可刪，bank 不受損）
- [ ] 非擁有者的 rename／delete → 404
- [ ] Dashboard 有端到端可操作的建立／改名／刪除入口（含破壞性確認）
- [ ] HTTP 測試覆蓋：CRUD、擁有權、刪除有 bank／無 bank 的 Group 後 bank 仍可查且視為未分組
