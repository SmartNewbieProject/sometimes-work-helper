"""
환경 설정 모듈
"""
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Slack 설정
    SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
    SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET')
    SLACK_CHANNEL_ID = os.getenv('SLACK_CHANNEL_ID')
    
    # OpenAI 설정  
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
    
    # Jira 설정
    JIRA_SERVER = os.getenv('JIRA_SERVER')
    JIRA_USER = os.getenv('JIRA_USER')
    JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')
    JIRA_PROJECT_KEY = os.getenv('JIRA_PROJECT_KEY')
    
    # AWS 설정
    AWS_REGION = os.getenv('AWS_REGION', 'ap-northeast-2')
    
    # Redis 설정 (중복 처리 방지용)
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    
    # DynamoDB 설정 (Redis 대안)
    DYNAMODB_TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME', 'workbot-processed-messages')
    
    # 로그 레벨
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # 메시지 처리 설정
    MESSAGE_LOOKBACK_MINUTES = int(os.getenv('MESSAGE_LOOKBACK_MINUTES', '5'))
    
    @classmethod
    def validate(cls):
        """필수 환경 변수 검증"""
        required = [
            cls.SLACK_BOT_TOKEN, cls.SLACK_SIGNING_SECRET, cls.SLACK_CHANNEL_ID,
            cls.JIRA_SERVER, cls.JIRA_USER, cls.JIRA_API_TOKEN, cls.JIRA_PROJECT_KEY,
            cls.OPENAI_API_KEY
        ]
        if not all(required):
            raise ValueError('필수 환경변수 누락')
        
        return True

config = Config()
