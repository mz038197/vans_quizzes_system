# 04 — 依 Group 篩選 dashboard（側欄 + 數量 + 響應式）

**What to build:** Dashboard 變成一致的單一畫面：左側側欄列出「全部」「未分組」與每個 Group（含數量）；點選後右側卡片格只顯示該集合。空 Group 仍顯示並標 (0)。小螢幕側欄改為卡片格上方的水平 chip 列。篩選下既有卡片操作（管理題目、看繳交、複製連結、啟停、刪除）維持可用。只顯示當前教師的 Group 與 Quiz Bank。

**Blocked by:** 03 — 把 Quiz Bank 歸入零個、一個或多個 Group

**Status:** ready-for-agent

- [ ] `GET /teacher-dashboard` 支援 `?group=<id|all|ungrouped>`；缺省等同「全部」
- [ ] 側欄含「全部」「未分組」與每個 Group，各自有正確 (N)；空 Group 為 (0)
- [ ] 「未分組」為查詢結果（無任何 Group 連結的 bank），不是資料庫哨兵列
- [ ] 點選側欄項目會驅動同一頁的卡片格（不是另一個頁面）
- [ ] 小螢幕改為水平 chip 列，資料與行為與側欄相同
- [ ] 僅當前教師的資料出現在側欄與格線
- [ ] 篩選啟用時，既有卡片操作仍可用（非回歸）
- [ ] HTTP／回應斷言偏高階：出現 Group 名稱、數量、正確卡片；不做 CSS／Jinja 內部細節斷言
