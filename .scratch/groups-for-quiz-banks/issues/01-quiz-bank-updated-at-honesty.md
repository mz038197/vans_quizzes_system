# 01 — 讓 Quiz Bank 的 updated_at 在每條變更路徑都誠實更新

**What to build:** 教師之後能依「編輯時間」排序的前提：每個會變更 Quiz Bank 的操作都明確寫入 `updated_at`，而不是只靠 ORM 的 onupdate。建立題庫、啟停、練習／計分／時限設定、題目增刪改、MD 匯入等路徑都要讓 `updated_at` 嚴格前進；刪除題庫則不適用。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] Quiz Bank 具備 `updated_at`（既有資料可為 null；新變更後必須有值）
- [ ] 每條會變更 Quiz Bank 的既有路徑都顯式設定 `updated_at`（含只動題目、只動關聯、可能踩不到 onupdate 的路徑）
- [ ] HTTP 測試覆蓋：上述路徑執行後，`updated_at` 嚴格大於變更前
- [ ] 不引入新的測試 seam；沿用既有 Flask test client + `app_context` 模式
