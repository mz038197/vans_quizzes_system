# 程式碼排序題型 - 程式碼格式修正

## 更新日期
2025-10-20

## 問題描述
程式碼排序題型中的程式碼區塊顯示時，縮排和換行格式沒有正確保留，導致程式碼看起來跑版。

### 原始問題
```
A p = 
2
while p &lt;= 100:
  is_prime = True
```

### 修正後效果
```
A  p = 
2
while p &lt;= 100:
    is_prime = True
```

## 修正內容

### 1. CSS 樣式修正 (`static/css/style.css`)

**修改前：**
```css
.code-block {
    white-space: pre-wrap;
}
```

**修改後：**
```css
.code-block {
    white-space: pre;
    overflow-x: auto;
    word-wrap: normal;
    word-break: normal;
    font-size: 14px;
}
```

### 2. 關鍵修改說明

#### `white-space: pre` vs `white-space: pre-wrap`
- **`pre`**: 保留所有空白字符（空格、Tab、換行），不自動換行
- **`pre-wrap`**: 保留空白字符，但會自動換行（這會導致縮排錯亂）

#### 添加 `overflow-x: auto`
- 當程式碼過長時，提供橫向滾動條
- 避免程式碼被強制換行

#### 統一字體大小
- 設定 `font-size: 14px`
- 確保所有地方的程式碼顯示大小一致

### 3. 修改的文件

1. **`static/css/style.css`**
   - 修改 `.code-block` 基礎樣式

2. **`templates/manage_quiz_bank.html`**
   - 修改老師查看題目時的程式碼區塊預覽樣式
   - 修改答案區中顯示的程式碼樣式

3. **`templates/result.html`**
   - 修改結果頁面中的程式碼顯示（新格式）
   - 修改結果頁面中的程式碼顯示（舊格式兼容）

### 4. 適用範圍

所有修正都同時應用於：
- ✅ 學生答題界面 - 可選程式碼區塊
- ✅ 學生答題界面 - 拖放到答案區的程式碼
- ✅ 老師查看題目 - 可選程式碼區塊
- ✅ 老師查看題目 - 答案區顯示的正確答案
- ✅ 結果頁面 - 所有程式碼顯示

## 技術細節

### 使用 `white-space: pre` 的優點
1. **完全保留格式**：所有空格、Tab、換行都會被保留
2. **縮排正確**：Python 等語言的縮排不會錯亂
3. **可預測性**：程式碼顯示與輸入時完全一致

### 處理長程式碼
- 添加 `overflow-x: auto` 提供橫向滾動
- 添加 `word-wrap: normal` 和 `word-break: normal` 防止自動換行
- 程式碼區塊會自動顯示滾動條，不會破壞格式

### 字體設置
```css
font-family: 'Courier New', monospace;
font-size: 14px;
line-height: 1.5;
```
- 使用等寬字體確保對齊
- 統一字體大小
- 適當的行高提高可讀性

## 測試案例

### 測試 1：Python 縮排
```python
A  p = 2
while p <= 100:
    is_prime = True
```

**預期結果**：所有縮排正確保留，空格不會消失

### 測試 2：多層縮排
```python
def factorial(n):
    if n <= 1:
        return 1
    else:
        return n * factorial(n-1)
```

**預期結果**：4空格縮排正確顯示

### 測試 3：混合空格和 Tab
```javascript
function hello() {
	console.log("Hello");    // Tab縮排
    console.log("World");    // 空格縮排
}
```

**預期結果**：Tab 和空格都正確顯示

### 測試 4：長行程式碼
```python
very_long_variable_name = some_function_with_many_parameters(param1, param2, param3, param4, param5)
```

**預期結果**：出現橫向滾動條，不自動換行

## 視覺效果對比

### 修正前（跑版）
```
程式碼區塊：
┌──────────────────────┐
│ A p = 2 while p &lt;=  │
│ 100: is_prime = True │  ❌ 換行錯誤
└──────────────────────┘
```

### 修正後（正確格式）
```
程式碼區塊：
┌────────────────────────┐
│ A  p = 2               │
│ while p <= 100:        │
│     is_prime = True    │  ✅ 格式正確
└────────────────────────┘
```

## 瀏覽器兼容性

`white-space: pre` 支援所有現代瀏覽器：
- ✅ Chrome/Edge
- ✅ Firefox
- ✅ Safari
- ✅ IE 6+

## 注意事項

1. **程式碼輸入時的格式很重要**
   - 老師在編輯題目時輸入的空格、Tab、換行都會被保留
   - 建議複製貼上程式碼時保持原始格式

2. **長程式碼的處理**
   - 超出容器寬度的程式碼會顯示橫向滾動條
   - 不建議使用過長的單行程式碼

3. **移動設備**
   - 橫向滾動在觸控設備上仍然可用
   - 建議程式碼行長度控制在合理範圍內

## 相關文件
- `PARSONS_UPDATE.md` - 原始功能更新說明
- `PARSONS_LAYOUT_FIX.md` - 排版優化說明

---

更新日期：2025-10-20

