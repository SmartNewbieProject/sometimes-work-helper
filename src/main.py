"""
메인 Lambda 핸들러
"""
import json
import logging
from typing import Dict, Any
from .config import config
from .slack_client import SlackClient
from .jira_client import JiraClient
from .openai_client import OpenAIClient
from .message_processor import MessageProcessor, extract_ticket_candidates
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
# from . import scheduler

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 전역 클라이언트 인스턴스 (Lambda 콜드 스타트 최적화)
slack_client = SlackClient()
jira_client = JiraClient()
openai_client = OpenAIClient()
message_processor = MessageProcessor()

app = FastAPI()

# @app.on_event("startup")
# def on_startup():
#     scheduler.start_scheduler()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/slack/interactions")
async def slack_interactions(request: Request):
    form = await request.form()
    payload = form.get('payload')
    if payload:
        payload_dict = json.loads(payload)
        logger.info(f"슬랙 인터랙션 payload: {payload_dict}")
        result = slack_client.handle_interaction(payload_dict)
        if result.get("ok"):
            return PlainTextResponse("티켓이 생성되었습니다.", status_code=200)
        else:
            return PlainTextResponse("티켓 생성에 실패했습니다.", status_code=200)
    return PlainTextResponse("No payload", status_code=400)

processed_event_ids = set()

@app.post("/slack/event")
async def slack_event(request: Request):
    body = await request.json()
    event_id = body.get("event_id")
    if event_id and event_id in processed_event_ids:
        logger.info(f"[app_mention] Duplicate event_id: {event_id}, skipping.")
        return JSONResponse(content={"ok": True})
    if event_id:
        processed_event_ids.add(event_id)
    if body.get("type") == "url_verification":
        return JSONResponse(content={"challenge": body.get("challenge")})
    if body.get("type") == "event_callback":
        event = body.get("event", {})
        if event.get("type") == "app_mention":
            user = event.get("user")
            text = event.get("text", "")
            ts = event.get("ts")
            thread_ts = event.get("thread_ts") or ts
            channel = event.get("channel")
            message = {
                "user": user,
                "text": text,
                "ts": ts,
                "thread_ts": thread_ts,
                "channel": channel
            }
            thread_context = slack_client.get_thread_context(thread_ts)
            logger.info(f"[app_mention] thread_context for ts={thread_ts}:\n{thread_context}")
            analysis_result = openai_client.analyze_thread_context(thread_context) if thread_context else None
            if analysis_result:
                if isinstance(analysis_result, list):
                    for candidate in analysis_result:
                        if candidate.get('need_ticket', False) and candidate.get('confidence', 0) > 0.5:
                            ticket_info = candidate['ticket_info']
                            approval_ts = slack_client.send_approval_message(ticket_info, message)
                            logger.info(f"[app_mention] Approval request sent: {approval_ts}")
                elif isinstance(analysis_result, dict):
                    if analysis_result.get('need_ticket', False) and analysis_result.get('confidence', 0) > 0.5:
                        ticket_info = analysis_result['ticket_info']
                        approval_ts = slack_client.send_approval_message(ticket_info, message)
                        logger.info(f"[app_mention] Approval request sent: {approval_ts}")
            return JSONResponse(content={"ok": True})
    return JSONResponse(content={"ok": True})

@app.get("/slack/event")
def slack_event_health():
    return {"status": "ok"}

def process_messages():
    """메시지를 처리하는 메인 로직"""
    try:
        logger.info(f"Fetching messages from last {config.MESSAGE_LOOKBACK_MINUTES} minutes")
        messages = slack_client.get_recent_messages(config.MESSAGE_LOOKBACK_MINUTES)
        if not messages:
            logger.info("No messages found")
            return {"processed": 0, "tickets_requested": 0}
        new_messages = message_processor.filter_new_messages(messages)
        if not new_messages:
            logger.info("No new messages to process")
            return {"processed": 0, "tickets_requested": 0}
        tickets_requested = 0
        for message in new_messages:
            try:
                user_name = slack_client.get_user_info(message['user']) or message['user']
                # thread_ts가 있으면 스레드 전체 문맥 분석, 아니면 기존 단일 메시지 분석
                if message.get('thread_ts'):
                    thread_context = slack_client.get_thread_context(message['thread_ts'])
                    logger.info(f"Thread context for ts={message['thread_ts']}:\n{thread_context}")
                    analysis_result = openai_client.analyze_thread_context(thread_context) if thread_context else None
                else:
                    logger.info(f"Analyzing message from {user_name}: {message['text'][:50]}...")
                    analysis_result = openai_client.analyze_message(message['text'], user_name)
                if not analysis_result:
                    logger.warning("Failed to analyze message")
                    continue
                if analysis_result.get('need_ticket', False) and analysis_result.get('confidence', 0) > 0.5:
                    logger.info(f"Requesting ticket creation for message: {analysis_result['reasoning']}")
                    ticket_info = analysis_result['ticket_info']
                    approval_ts = slack_client.send_approval_message(ticket_info, message)
                    if approval_ts:
                        tickets_requested += 1
                        logger.info(f"Approval request sent: {approval_ts}")
                message_processor.mark_message_processed(message['_hash'], {
                    'user': user_name,
                    'text': message['text'],
                    'analysis': analysis_result
                })
            except Exception as e:
                logger.error(f"Failed to process message: {e}")
                continue
        logger.info(f"Processed {len(new_messages)} messages, requested {tickets_requested} tickets")
        return {"processed": len(new_messages), "tickets_requested": tickets_requested}
    except Exception as e:
        logger.error(f"Failed to process messages: {e}")
        raise

# 로컬 테스트용
if __name__ == "__main__":
    import os
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    
    result = lambda_handler({}, None)
    print(json.dumps(result, indent=2, ensure_ascii=False))

# 기존 Lambda 핸들러 및 단발성 실행부는 주석 처리
# def lambda_handler(...):
#     ...
