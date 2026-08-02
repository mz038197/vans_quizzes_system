# 05 — 依編輯時間或名稱排序 dashboard

**What to build:** 卡片格上方有排序控制：依編輯時間（最近編輯在前）或依名稱（A→Z）。切換側欄 Group 時排序選擇維持不變。同鍵時以穩定次序打破平手，避免每次重載亂跳。缺省為「全部 + 編輯時間」。

**Blocked by:** 01 — 讓 Quiz Bank 的 updated_at 在每條變更路徑都誠實更新；04 — 依 Group 篩選 dashboard（側欄 + 數量 + 響應式）

**Status:** ready-for-agent

- [ ] `GET /teacher-dashboard` 支援 `?sort=<updated_desc|name_asc>`；缺省為 `updated_desc`
- [ ] 卡片格上方有對應的排序控制，且在切換側欄項目後仍保留選擇
- [ ] 編輯時間排序反映真實編輯（含歸屬變更等會 bump `updated_at` 的操作），不是建立時間
- [ ] 排序鍵相同時以 `id ASC` 穩定打破平手
- [ ] HTTP 測試覆蓋：兩種 sort、缺省行為、穩定平手次序
