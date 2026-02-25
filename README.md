# Tw_Stock_Degen (台股 Degen AI 分析機器人)

這是一個專為台灣散戶設計的「AI 投顧老師」Line Bot。透過臺灣證券交易所 (TWSE) OpenAPI 獲取每日個股行情，並由 Google Gemini 2.0 AI 化身為極具迷因風格的地下投顧/鄉民，給予充滿娛樂性的盤後分析與走勢嘴砲。

## 🚀 快速開始

### 1. 前置作業
- 申請 **LINE Developer** 帳號，建立一個 Messaging API Channel。
- 獲取 **Line Channel Secret** 以及 **Line Channel Access Token**。
- 申請 **Google Gemini API Key**。

### 2. 環境設定
複製一份環境變數範例檔：
```bash
cp .env.example .env
```
編輯 `.env` 檔案，填入您剛剛申請的 API Keys。

### 3. 安裝相依套件
建議使用虛擬環境 (Virtual Environment)：
```bash
python -m venv .venv
.\.venv\Scripts\activate   # Windows
# source .venv/bin/activate # Mac/Linux

pip install -r requirements.txt
```

### 4. 啟動伺服器
```bash
uvicorn main:app --reload --port 8000
```

### 5. 測試與上線 (ngrok)
若要在本地端測試 Line Webhook，您可以使用 `ngrok`：
```bash
ngrok http 8000
```
完成後，將 ngrok 產生的 `https://...` 網址加上 `/callback`，填入 Line Developer 後台的 **Webhook URL** 欄位（例如 `https://xxxx.ngrok-free.app/callback`），並開啟「Use webhook」功能。

## 💡 使用方式
在 Line 中加此 Bot 為好友，直接輸入台股代號（例如 `2330` 或 `0050`），AI 老師就會開始幫你解籤！
