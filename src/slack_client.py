"""
Slack API 클라이언트 모듈
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from .config import config
import os
from .jira_client import JiraClient
import traceback

logger = logging.getLogger(__name__)

class SlackClient:
    def __init__(self):
        self.client = WebClient(token=config.SLACK_BOT_TOKEN)
        self.app = App(token=config.SLACK_BOT_TOKEN, signing_secret=config.SLACK_SIGNING_SECRET)
        self.jira = JiraClient()
        
    def get_recent_messages(self, minutes: int = 5) -> List[Dict]:
        """
        최근 n분간의 메시지를 가져옵니다.
        
        Args:
            minutes: 조회할 시간 범위 (분)
            
        Returns:
            메시지 리스트
        """
        try:
            # 현재 시간에서 minutes만큼 뺀 시간을 타임스탬프로 변환
            oldest = datetime.now() - timedelta(minutes=minutes)
            oldest_ts = oldest.timestamp()
            
            # 채널 히스토리 조회
            response = self.client.conversations_history(
                channel=config.SLACK_CHANNEL_ID,
                oldest=str(oldest_ts),
                limit=100
            )
            
            messages = []
            if response["ok"]:
                for message in response["messages"]:
                    # 봇 메시지나 시스템 메시지는 제외
                    if message.get("subtype") in ["bot_message", "channel_join", "channel_leave"]:
                        continue
                    
                    messages.append({
                        "ts": message["ts"],
                        "user": message.get("user", "unknown"),
                        "text": message.get("text", ""),
                        "thread_ts": message.get("thread_ts"),
                        "timestamp": datetime.fromtimestamp(float(message["ts"]))
                    })
                    
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get recent messages: {e}")
            return []
    
    def send_approval_message(self, ticket_info: Dict, original_message: Dict) -> Optional[str]:
        """
        티켓 생성 승인을 요청하는 인터랙티브 메시지를 전송합니다.
        
        Args:
            ticket_info: 생성할 티켓 정보
            original_message: 원본 메시지 정보
            
        Returns:
            전송된 메시지의 타임스탬프
        """
        try:
            logger.info(f"슬랙 티켓 생성 요청 메시지 전송 시도: {ticket_info['summary']}")
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🎫 *티켓 생성 요청*\n\n*제목:* {ticket_info['summary']}\n*유형:* {ticket_info['issue_type']}\n*우선순위:* {ticket_info['priority']}\n*담당자:* {ticket_info['assignee']}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ 예, 생성하겠습니다"
                            },
                            "style": "primary",
                            "action_id": "create_ticket",
                            "value": json.dumps(ticket_info, ensure_ascii=False)
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "❌ 생략할게요."
                            },
                            "style": "danger",
                            "action_id": "skip_ticket",
                            "value": json.dumps(ticket_info, ensure_ascii=False)
                        }
                    ]
                }
            ]
            response = self.client.chat_postMessage(
                channel=config.SLACK_CHANNEL_ID,
                blocks=blocks,
                text="티켓 생성 요청"
            )
            logger.info(f"슬랙 응답: {response}")
            if response["ok"]:
                return response["ts"]
            else:
                logger.error(f"슬랙 메시지 전송 실패: {response.get('error')}")
        except Exception as e:
            logger.error(f"Failed to send approval message: {e}\n{traceback.format_exc()}")
        return None
    
    def get_user_info(self, user_id: str) -> Optional[str]:
        """사용자 정보를 가져옵니다."""
        try:
            response = self.client.users_info(user=user_id)
            if response["ok"]:
                return response["user"]["real_name"] or response["user"]["name"]
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
        return None

    def handle_interaction(self, payload: Dict) -> Dict:
        """
        슬랙 인터랙션 payload를 받아 Jira 티켓을 생성하고, 결과를 반환합니다.
        """
        try:
            actions = payload.get('actions', [])
            if not actions:
                return {"ok": False, "error": "No actions in payload"}
            action = actions[0]
            if action.get('action_id') == 'create_ticket':
                ticket_info = json.loads(action.get('value'))
                issue_key = self.jira.create_ticket(
                    summary=ticket_info['summary'],
                    description=ticket_info['description'],
                    issue_type=ticket_info.get('issue_type', '작업'),
                    assignee=ticket_info.get('assignee'),
                    priority=ticket_info.get('priority')
                )
                channel_id = payload.get('channel', {}).get('id')
                user_id = payload.get('user', {}).get('id')
                message_ts = payload.get('message', {}).get('ts')
                if issue_key and channel_id and message_ts:
                    jira_url = f"https://{config.JIRA_SERVER.replace('https://', '')}/browse/{issue_key}"
                    assignee = ticket_info.get('assignee', '')
                    update_text = f"[{assignee}] Jira 티켓이 생성되었습니다: {issue_key} (<{jira_url}|링크>)"
                    self.client.chat_update(
                        channel=channel_id,
                        ts=message_ts,
                        text=update_text,
                        blocks=[{
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": update_text}
                        }]
                    )
                    return {"ok": True, "issue_key": issue_key}
                else:
                    return {"ok": False, "error": "Jira 티켓 생성 실패"}
            elif action.get('action_id') == 'skip_ticket':
                channel_id = payload.get('channel', {}).get('id')
                message_ts = payload.get('message', {}).get('ts')
                if channel_id and message_ts:
                    self.client.chat_delete(
                        channel=channel_id,
                        ts=message_ts
                    )
                    return {"ok": True, "skipped": True}
                else:
                    return {"ok": False, "error": "메시지 삭제 실패"}
            return {"ok": False, "error": "Unknown action_id"}
        except Exception as e:
            logger.error(f"Failed to handle interaction: {e}\n{traceback.format_exc()}")
            return {"ok": False, "error": str(e)}

    def get_thread_context(self, thread_ts: str) -> Optional[str]:
        try:
            response = self.client.conversations_replies(
                channel=config.SLACK_CHANNEL_ID,
                ts=thread_ts,
                limit=100
            )
            if not response["ok"]:
                return None
            messages = response["messages"]
            # 시간순 정렬
            messages = sorted(messages, key=lambda m: float(m["ts"]))
            context_lines = []
            for m in messages:
                user = m.get("user", "unknown")
                text = m.get("text", "")
                context_lines.append(f"[{user}] {text}")
            return "\n".join(context_lines)
        except Exception as e:
            logger.error(f"Failed to get thread context: {e}\n{traceback.format_exc()}")
            return None

