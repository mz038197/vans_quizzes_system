# 📚 線上題庫系統

一個現代化的線上測驗平台，專為教師和學生設計，支援多種題型包括程式碼排序題(Parsons Puzzle)。

## ✨ 功能特色

### 👨‍🏫 教師功能
- **用戶管理**: 簡單的註冊登入系統
- **題庫管理**: 建立、編輯、刪除題庫
- **多種題型**: 支援5種不同的題目類型
- **成績統計**: 詳細的成績分析和統計圖表
- **結果匯出**: CSV格式匯出成績資料
- **即時分享**: 透過簡單的題庫代碼分享給學生

### 👨‍🎓 學生功能
- **無需註冊**: 使用題庫代碼直接參與測驗
- **多種題型**: 豐富的答題體驗
- **即時評分**: 測驗完成後立即查看成績
- **詳細結果**: 包含正確答案對照的詳細結果頁面

### 📝 支援題型
1. **單選題**: 傳統的選擇題
2. **多選題**: 支援多個正確答案
3. **填空題**: 文字輸入答案
4. **下拉選單**: 從預設選項中選擇
5. **程式碼排序題** (Parsons Puzzle): 拖拉排序程式碼片段

## 🚀 快速開始

### 環境需求
- Python 3.7+
- pip
- PostgreSQL (僅生產環境)

### 安裝步驟

1. **安裝依賴套件**
```bash
pip install -r requirements.txt
```

2. **設置環境變數**
```bash
# 開發環境（教師登入使用本機的假 router 頁面）
export FLASK_ENV=development

# 生產環境：見下方「環境變數設定」
```

3. **啟動應用程式**
```bash
# 開發環境
python app.py

# 生產環境
gunicorn app:app
```

4. **開啟瀏覽器**
訪問 `http://localhost:5000`

### 初次使用

1. **教師註冊**: 點擊「註冊」建立教師帳號
2. **建立題庫**: 登入後點擊「新增題庫」
3. **新增題目**: 在題庫管理頁面新增各種類型的題目
4. **分享給學生**: 複製題庫連結或題庫代碼給學生
5. **查看成績**: 在成績頁面查看學生的作答結果

## 🔧 技術架構

### 後端技術
- **框架**: Flask (Python)
- **資料庫**: SQLite (可升級至PostgreSQL)
- **ORM**: SQLAlchemy
- **教師登入**: 透過 vans_coding_router 的 OAuth（`openid teacher`，Google），本系統不存帳號（ADR 0007）
- **表單處理**: WTForms

### 前端技術
- **樣式**: 自製CSS (現代化設計)
- **互動**: 原生JavaScript
- **拖拉功能**: HTML5 Drag & Drop API
- **響應式設計**: 支援手機和平板

### 資料庫設計
- **User**: 用戶資料表
- **QuizBank**: 題庫資料表
- **Question**: 題目資料表
- **Submission**: 作答記錄表

## 📱 程式碼排序題 (Parsons Puzzle)

這是本系統的特色功能，讓學生通過拖拉程式碼片段來學習程式設計邏輯。

### 使用方式
1. 教師準備程式碼片段
2. 系統自動打亂順序
3. 學生拖拉片段到正確位置
4. 自動評分比較順序

### 教育價值
- 培養程式邏輯思維
- 降低程式語法門檻
- 適合初學者學習

## 📊 成績統計功能

### 統計指標
- 總作答人數
- 平均分數
- 最高分數
- 及格率 (60分以上)
- 排名系統

### 匯出功能
- CSV格式下載
- 包含完整作答資料
- 適合進一步分析

## 🔐 安全考量

- 密碼雜湊儲存
- 用戶權限控制
- CSRF保護
- SQL注入防護

## 🎨 使用者體驗

- 響應式設計，支援各種裝置
- 直觀的操作介面
- 即時回饋和提示
- 優雅的載入動畫

## 🚀 部署建議

### 開發環境
- 使用內建的SQLite資料庫
- 預設在localhost:5000運行
- 設置 `FLASK_ENV=development`

### 生產環境
- 使用PostgreSQL資料庫
- 設置 `FLASK_ENV=production`
- 使用Gunicorn作為WSGI伺服器
- 配置反向代理 (如Nginx)
- 適合部署在Render.com等雲端平台

### 環境變數設定

| 變數 | 何時需要 | 說明 |
|---|---|---|
| `FLASK_ENV` | 一律必填 | 只能是 `production` 或 `development`。沒設定或拼錯時，程式拒絕啟動：預設值會打開開發用的假登入頁。 |
| `SECRET_KEY` | 正式環境必填 | 至少 32 個字元的隨機值。它簽章教師 cookie；太短或用預設值時，正式環境會拒絕啟動。 |
| `DATABASE_URL` | 正式環境必填 | PostgreSQL 連線字串 |
| `QUIZZES_OAUTH_CLIENT_SECRET` | 正式環境必填 | router 上 `quizzes` OAuth Client 的 secret。router 只存它的 SHA-256。 |
| `ROUTER_URL` | 選填 | 預設 `https://ai.vanscoding.com`。開發環境沒設定時，改用本機的假 router 登入頁。 |
| `PUBLIC_URL` | 選填 | 預設 `https://quizzes.vanscoding.com`。用來組 callback 網址與檢查 `Origin`。 |
| `QUIZZES_OAUTH_CLIENT_ID` | 選填 | 預設 `quizzes` |
| `QUIZZES_DEV_DATABASE_URL` | 選填（開發、測試） | 預設 `sqlite:///quiz_platform.db` |

### 教師登入

- 老師在首頁按「用 Google 登入（vcrouter）」，經 router 登入。只有在 router 有 teacher 或 admin 角色的人能登入。
- 學生不登入。學生用題庫連結 `/quiz/<access_code>` 作答，交卷後拿到不能猜的成績連結 `/result/<result_token>`（ADR 0008）。
- 本機開發不必跑 router：沒有設定 `ROUTER_URL` 時，`/auth/login` 會轉到 `/dev/fake-router/authorize`，輸入任意 router 使用者編號即可登入。正式環境沒有這一頁。

### Render.com部署指南
1. 在Render.com建立新的Web Service
2. 連接到您的GitHub倉庫
3. 設定環境變數：
   - `FLASK_ENV=production`
   - `SECRET_KEY=<至少 32 個字元的隨機值>`
   - `DATABASE_URL=postgresql://...`
   - `QUIZZES_OAUTH_CLIENT_SECRET=<router 上 quizzes client 的 secret>`
4. 設定啟動命令：`gunicorn app:app`
5. 建立服務並等待部署完成

## 📝 授權

本專案使用 MIT 授權條款。

## 🤝 貢獻

歡迎提交問題報告和功能建議！

## 📞 技術支援

如有任何問題，請提交 Issue 或聯繫開發團隊。

---

**開發團隊**: 專為教育而設計 💡
