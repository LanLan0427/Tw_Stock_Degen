import os
import requests
import json
import urllib3
from datetime import datetime
from google import genai
from google.genai import types
from google.genai.errors import APIError
from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# 忽略因為 verify=False 產生的警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Environment ──────────────────────────────────────────────────────
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None
    print("Warning: GEMINI_API_KEY is not set.")

# ── Prompts ──────────────────────────────────────────────────────────
SYSTEM_INSTRUCTION = """
你是一個在台灣 PTT 股版（Stock版）打滾多年，同時又帶有一點「地下投顧老師」氣息的資深股民。
你的說話風格：
1. **非常接地氣、愛用鄉民用語**：例如「水鬼」、「抓交替」、「韭菜」、「畢業」、「歐印（All in）」、「丸子（完了）」、「相信神山」、「台灣價值」、「咕嚕咕嚕」。
2. **浮誇且略帶嘲諷或極度樂觀**：喜歡講「好的老師帶你上天堂，不好的老師帶你住套房」、「這檔早就叫你買了你不聽！」、「送分題」、「天上掉下來的禮物」。
3. **專業術語交雜幹話**：會講解一些基本的技術面（收盤價、漲跌幅、成交量），但結尾總是會給出一個超主觀（Degen）的個人判斷。
4. **絕對使用繁體中文（台灣習慣用語）**。

你的任務是：
接收使用者提供的「台股代號」與「今日盤後數據」，並給出一段**精簡有力（約 100~150 字內，因為是 Line 訊息）**的走勢點評。
最後必須附上一句非常有梗的「老師結論」或「鄉民箴言」。
"""

# ── Data Fetching & Charting ─────────────────────────────────────────
def fetch_twse_stock_data(symbol: str) -> dict | None:
    """
    從台灣證券交易所 OpenAPI 獲取個股日收盤行情 (STOCK_DAY_ALL)。
    這支 API 包含所有股票當日的收盤資訊。
    API 網址: https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL
    """
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        # TWSE OpenAPI 有時會有憑證問題，特別是在某些 Windows 環境下
        # 這裡設定 verify=False 來暫時忽略 SSL 憑證檢查
        response = requests.get(url, verify=False)
        response.raise_for_status()
        data = response.json()
        
        # 尋找指定股票代號的數據
        for stock in data:
            if stock.get("Code") == symbol:
                return stock
                
        return None # 找不到該股票
    except Exception as e:
        print(f"Error fetching TWSE data: {e}")
        return None

# ── AI Analysis ──────────────────────────────────────────────────────
async def analyze_stock(symbol: str) -> str:
    """主函數：取得數據並呼叫 Gemini 產生分析，回傳純文字訊息"""
    
    if not client:
        return "老師的腦袋當機了（尚未設定 Gemini API Key）"

    # 1. 取得 TWSE 數據
    stock_data = fetch_twse_stock_data(symbol)
    if not stock_data:
         return f"同學，你在找哪一檔？台股沒有 `{symbol}` 這支股票啦！是不是打錯了？"

    # stock_data 範例結構:
    # {
    #   "Code": "2330",
    #   "Name": "台積電",
    #   "TradeVolume": "...?",
    #   "TradeValue": "...",
    #   "OpeningPrice": "...",
    #   "HighestPrice": "...",
    #   "LowestPrice": "...",
    #   "ClosingPrice": "900.00",
    #   "Change": "+10.00",
    #   "Transaction": "..."
    # }

    # 2. 組合給 AI 的分析資訊
    stock_name = stock_data.get("Name", "未知")
    close_price = stock_data.get("ClosingPrice", "未知")
    price_change = stock_data.get("Change", "未知")
    trade_vol = stock_data.get("TradeVolume", "未知")
    
    # Generate Chart
    chart_filename = generate_stock_chart(symbol, stock_name)

    prompt = f"""
    請針對以下台股今日盤後數據給出短評：
    - 代號：{symbol}
    - 股名：{stock_name}
    - 收盤價：{close_price}
    - 漲跌：{price_change}
    - 成交股數：{trade_vol}

    請用語氣浮誇的「地下投顧老師/PTT鄉民」風格進行點評！(限 150 字內)
    """

    # 3. 呼叫 Gemini 2.0 API (加入 Retry 機制處理 503 或 Rate Limit)
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(APIError) 
        # google-genai 會將 503/429 拋出為 APIError
    )
    def call_gemini_with_retry(prompt_text):
        return client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.8,
            )
        )

    # 4. 組合最終回覆訊息
    # 先用語氣比較正經/美觀的格式列出基本資訊
    header = (
        f"📊 【{symbol} {stock_name}】今日實況\n"
        f"──────────────────\n"
        f"🔹 收盤價：{close_price}\n"
        f"🔹 漲跌幅：{price_change}\n"
        f"🔹 成交量：{trade_vol} 股\n"
        f"──────────────────\n\n"
        f"🎤 老師開示：\n"
    )

    try:
        response = call_gemini_with_retry(prompt)
        if response and response.text:
            final_text = header + response.text
            return final_text
        else:
            final_text = header + "老師目前沒有想法，改天再說啦！"
            return final_text
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        final_text = header + "老師今天喉嚨痛，沒辦法講話（AI 分析發生錯誤，請稍後再試）。"
        return final_text
