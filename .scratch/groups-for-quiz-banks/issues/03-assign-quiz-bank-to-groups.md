# 03 — 把 Quiz Bank 歸入零個、一個或多個 Group

**What to build:** 同一份 Quiz Bank 可同時屬於多個 Group（例如「110-1 段考」與「國三總複習」）。建立題庫時可選 Group；之後在 dashboard 卡片用「管理群組」modal 一次改完整歸屬。已有 Submission 的 bank 一樣可歸檔。變更歸屬會更新該 bank 的編輯時間。

**Blocked by:** 02 — 教師可建立、重新命名、刪除自己的 Group

**Status:** ready-for-agent

- [ ] `POST /api/quiz-bank/<id>/groups` 以 `{group_ids: [...]}` **整份覆寫**歸屬（非合併）；非擁有 bank → 404；任一 group 非同教師 → 400
- [ ] `POST /create-quiz-bank` 可選 `group_ids`；缺省或空陣列行為與現況相同（向後相容）
- [ ] 建立表單有可選的 Group 多選
- [ ] 卡片「管理群組」modal：列出教師所有 Group、預勾目前歸屬、單一「儲存」送出完整清單；尚無 Group 時可就地建立
- [ ] 變更歸屬後該 Quiz Bank 的 `updated_at` 嚴格前進
- [ ] HTTP 測試覆蓋：建立時指定、modal／API 覆寫語意、擁有權錯誤、有 Submission 的 bank 可歸檔
