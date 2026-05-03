"""FastAPI entrypoint：企业微信回调接收 + URL 验签 + 健康检查。

关键设计：
  - POST /wechat/callback 必须 5 秒内返回 'success'，业务逻辑全走 BackgroundTasks。
  - GET /wechat/callback 用于企业微信首次配置 URL 时的回显验签。
  - 启动时 setup_logger 配置 loguru。
"""

from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import get_settings
from app.crypto import WXBizMsgCrypt, WXBizMsgCryptError
from app.handlers import handle_callback_event
from app.utils.logger import logger, setup_logger

setup_logger()

app = FastAPI(title="WeChat Channels Parser", version="0.1.0")


def _crypto() -> WXBizMsgCrypt:
    s = get_settings()
    return WXBizMsgCrypt(
        token=s.wechat_callback_token,
        encoding_aes_key=s.wechat_callback_aes_key,
        receive_id=s.wechat_corp_id,
    )


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/wechat/callback", response_class=PlainTextResponse)
async def verify_callback(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
) -> str:
    """企业微信首次配置回调 URL 时的验签端点。"""
    try:
        return _crypto().verify_url(msg_signature, timestamp, nonce, echostr)
    except WXBizMsgCryptError as exc:
        logger.warning(f"verify_url failed: {exc}")
        raise HTTPException(status_code=401, detail="signature verify failed") from exc


@app.post("/wechat/callback", response_class=PlainTextResponse)
async def receive_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
) -> str:
    """收到推送 → 立即解密拿事件 → 后台处理 → 5 秒内返回 'success'。"""
    body = await request.body()
    try:
        event = _crypto().decrypt_msg(msg_signature, timestamp, nonce, body.decode("utf-8"))
    except WXBizMsgCryptError as exc:
        logger.warning(f"decrypt_msg failed: {exc}")
        raise HTTPException(status_code=400, detail="decrypt failed") from exc

    logger.info("callback_received", extra={"event": event})
    background_tasks.add_task(_safe_handle, event)
    return "success"


async def _safe_handle(event: dict) -> None:
    """Background-task wrapper — never let an exception escape into the void."""
    try:
        await handle_callback_event(event)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"handle_callback_event failed: {exc}")
