"""
Jira API 클라이언트 모듈
"""
import logging
from typing import Dict, Optional
from jira import JIRA
from .config import config

logger = logging.getLogger(__name__)

class JiraClient:
    def __init__(self):
        """Jira 클라이언트 초기화"""
        try:
            options = {'server': config.JIRA_SERVER}
            self.jira = JIRA(options, basic_auth=(config.JIRA_USER, config.JIRA_API_TOKEN))
            logger.info("Jira client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Jira client: {e}")
            raise
    
    def create_ticket(self, summary: str, description: str, issue_type: str = '작업', project_key: str = None, assignee: str = None, priority: str = None) -> Optional[str]:
        valid_types = ["작업", "버그", "스토리"]
        ISSUE_TYPE_ID_MAP = {
            "작업": "10021",
            "버그": "10022",
            "스토리": "10023"
        }
        JIRA_PRIORITIES = {"Highest", "High", "Medium", "Low"}
        if issue_type not in valid_types:
            issue_type = "작업"
        issue_type_id = ISSUE_TYPE_ID_MAP.get(issue_type, "10021")
        fields = {
            'project': {'key': project_key or config.JIRA_PROJECT_KEY},
            'summary': summary,
            'description': description,
            'issuetype': {'id': issue_type_id},
        }
        if assignee:
            fields['assignee'] = {'name': assignee}
        priority = (priority or "Medium")
        if priority not in JIRA_PRIORITIES:
            logger.warning(f"허용되지 않는 priority 값: {priority}, 기본값 'Medium'으로 대체")
            priority = "Medium"
        fields['priority'] = {'name': priority}
        try:
            issue = self.jira.create_issue(fields=fields)
            return issue.key
        except Exception as e:
            logger.error(f"Failed to create Jira issue: {e}")
            return None
    
    def _get_assignee_account_id(self, assignee_name: str) -> Optional[str]:
        """담당자 이름을 계정 ID로 변환합니다."""
        try:
            # 간단한 매핑 (실제 환경에서는 Jira API로 사용자 검색)
            name_mapping = {
                "최은기": "eunki.choi", 
                "유재윤": "jaeyoon.yu"
            }
            return name_mapping.get(assignee_name, assignee_name)
        except Exception as e:
            logger.error(f"Failed to get assignee account ID: {e}")
            return None

    def get_recent_tickets(self, max_results: int = 30) -> list:
        """최근 생성된 티켓의 summary/description 리스트 반환"""
        try:
            issues = self.jira.search_issues(f'project={config.JIRA_PROJECT_KEY} ORDER BY created DESC', maxResults=max_results, fields='summary,description')
            ticket_list = []
            for issue in issues:
                ticket_list.append({
                    'key': issue.key,
                    'summary': getattr(issue.fields, 'summary', ''),
                    'description': getattr(issue.fields, 'description', '') or ''
                })
            return ticket_list
        except Exception as e:
            logger.error(f"Failed to fetch recent Jira tickets: {e}")
            return []
