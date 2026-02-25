import os
import logging
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from src.stock_analyzer import analyze_stock

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Environment ──────────────────────────────────────────────────────
load_dotenv()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    logger.warning("Line Messaging API keys are missing. Please set them in .env")

# ── Line Bot Setup ───────────────────────────────────────────────────
app = FastAPI(title="Tw_Stock_Degen API")

if LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN:
    configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    async_api_client = AsyncApiClient(configuration)
    line_bot_api = AsyncMessagingApi(async_api_client)
    parser = WebhookParser(LINE_CHANNEL_SECRET)
else:
    logger.error("Skipping Line Bot Initialization due to missing config.")
    parser = None
    line_bot_api = None


# ── Webhook Endpoint ─────────────────────────────────────────────────
@app.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks):
    if not parser or not line_bot_api:
        raise HTTPException(status_code=500, detail="Line Bot not configured.")

    signature = request.headers.get("X-Line-Signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Signature missing.")

    body = await request.body()
    body_str = body.decode("utf-8")
    
    try:
        events = parser.parse(body_str, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature. Check your channel secret.")
        raise HTTPException(status_code=400, detail="Invalid signature.")
    
    for event in events:
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue
            
        user_message = event.message.text.strip()
        reply_token = event.reply_token
        
        # We will dispatch the heavy processing (fetching data + AI generation)
        # to a background task so we can return 200 OK to Line immediately.
        background_tasks.add_task(handle_message, user_message, reply_token)

    return JSONResponse(content={"status": "ok"})


# ── Message Handler ──────────────────────────────────────────────────
async def handle_message(user_message: str, reply_token: str):
    logger.info(f"Processing message: {user_message}")
    
    messages_to_send = []
    
    try:
        # TODO: A simple heuristic to detect stock symbols. 
        # For now, if the message is roughly digits or starts with "分析", process it.
        # This will be refined.
        symbol = extract_symbol(user_message)
        
        if not symbol:
            reply_text = "老師聽不懂啦！請輸入台股代號，例如：`2330` 或是 `分析 2330`。"
            messages_to_send.append(TextMessage(text=reply_text))
        else:
            # 呼叫我們的分析 Agent，回傳純文字
            reply_text = await analyze_stock(symbol)
            messages_to_send.append(TextMessage(text=reply_text))
            
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        reply_text = "⚠️ 老師的系統當機了...（可能查無此檔股票或網路異常）"
        messages_to_send.append(TextMessage(text=reply_text))

    # Send reply back to Line
    try:
         await line_bot_api.reply_message(
             ReplyMessageRequest(
                 replyToken=reply_token,
                 messages=messages_to_send
             )
         )
         logger.info(f"Successfully replied for {user_message}")
    except Exception as e:
         logger.error(f"Failed to send reply to Line: {e}")

def extract_symbol(text: str) -> str | None:
    # 簡單過濾：移除 "分析" 兩字及空白符號
    # 不再限制只能是英數字，以便支援如「台積電」、「長榮」等中文名稱
    cleaned = text.replace("分析", "").replace(" ", "").strip()
    
    # 假設股票代號或名稱長度介於 2 ~ 10 個字之間
    if 2 <= len(cleaned) <= 10:
        return cleaned
        
    return None

@app.get("/")
async def root():
    return {"message": "Tw_Stock_Degen is running. Webhook endpoint is at /callback"}
