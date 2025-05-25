"""
메시지 처리 및 중복 방지 모듈
"""
import json
import logging
import hashlib
import boto3
from typing import List, Dict, Set, Optional
from datetime import datetime
from .config import config
import os
from .openai_client import classify_messages
from .jira_client import JiraClient

logger = logging.getLogger(__name__)

PROMPT_PATH = os.path.join(os.path.dirname(__file__), '../prompts/system_prompt.txt')

def load_system_prompt():
    with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
        return f.read()

jira_client = JiraClient()

def extract_ticket_candidates(messages):
    system_prompt = load_system_prompt()
    recent_tickets = jira_client.get_recent_tickets(max_results=30)
    logger.info(f"messages: {messages}")
    return classify_messages(messages, system_prompt, recent_tickets)

class MessageProcessor:
    def __init__(self):
        """메시지 처리기 초기화"""
        self.processed_messages: Set[str] = set()
        
        # DynamoDB 클라이언트 초기화 (중복 처리 방지용)
        try:
            self.dynamodb = boto3.resource('dynamodb', region_name=config.AWS_REGION)
            self.table = self.dynamodb.Table(config.DYNAMODB_TABLE_NAME)
        except Exception as e:
            logger.warning(f"Failed to initialize DynamoDB: {e}")
            self.dynamodb = None
            self.table = None
    
    def get_message_hash(self, message: Dict) -> str:
        """메시지의 고유 해시를 생성합니다."""
        content = f"{message['user']}_{message['text']}_{message['ts']}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def is_message_processed(self, message_hash: str) -> bool:
        """메시지가 이미 처리되었는지 확인합니다."""
        # 메모리에서 먼저 확인
        if message_hash in self.processed_messages:
            return True
        
        # DynamoDB에서 확인
        if self.table:
            try:
                response = self.table.get_item(Key={'message_hash': message_hash})
                return 'Item' in response
            except Exception as e:
                logger.error(f"Failed to check message in DynamoDB: {e}")
        
        return False
    
    def mark_message_processed(self, message_hash: str, message_data: Dict):
        """메시지를 처리된 것으로 표시합니다."""
        # 메모리에 추가
        self.processed_messages.add(message_hash)
        
        # DynamoDB에 저장
        if self.table:
            try:
                self.table.put_item(
                    Item={
                        'message_hash': message_hash,
                        'processed_at': datetime.now().isoformat(),
                        'message_data': json.dumps(message_data, ensure_ascii=False),
                        'ttl': int((datetime.now().timestamp() + 86400))  # 24시간 후 자동 삭제
                    }
                )
            except Exception as e:
                logger.error(f"Failed to save message to DynamoDB: {e}")
    
    def filter_new_messages(self, messages: List[Dict]) -> List[Dict]:
        """새로운 메시지만 필터링합니다. (DynamoDB에 없는 _hash만 반환)"""
        new_messages = []
        for message in messages:
            message_hash = self.get_message_hash(message)
            message['_hash'] = message_hash
            if not self.is_message_processed(message_hash):
                new_messages.append(message)
        logger.info(f"Filtered {len(new_messages)} new messages from {len(messages)} total messages")
        return new_messages
