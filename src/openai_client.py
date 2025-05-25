"""
OpenAI API 클라이언트 모듈
"""
import json
import logging
from typing import Dict, Optional, List
from openai import OpenAI
from .config import config, BASE_DIR
import openai
import os
import traceback

logger = logging.getLogger(__name__)

class OpenAIClient:
    def __init__(self):
        """OpenAI 클라이언트 초기화"""
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        
        # 시스템 프롬프트 로드
        try:
            prompt_path = os.path.join(BASE_DIR, 'prompts', 'system_prompt.txt')
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            self.system_prompt = "You are a helpful assistant for analyzing Slack messages and creating Jira tickets."
    
    def analyze_message(self, message_text: str, user_name: str = "") -> Optional[Dict]:
        """
        메시지를 분석하여 티켓 생성 필요성을 판단합니다.
        
        Args:
            message_text: 분석할 메시지 텍스트
            user_name: 메시지 작성자 이름
            
        Returns:
            분석 결과 딕셔너리
        """
        try:
            prompt = f"""
사용자: {user_name}
메시지: {message_text}

위 메시지를 분석하여 Jira 티켓 생성이 필요한지 판단하고, 필요하다면 티켓 정보를 생성해주세요.
"""
            
            response = self.client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            # JSON 응답 파싱
            content = response.choices[0].message.content
            
            # JSON 추출 (```json ... ``` 형태인 경우 처리)
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_str = content[start:end].strip()
            else:
                json_str = content.strip()
            
            result = json.loads(json_str)
            
            logger.info(f"OpenAI analysis result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze message with OpenAI: {e}")
            return None

    def analyze_thread_context(self, thread_context: str) -> Optional[Dict]:
        """
        스레드 전체 대화문맥을 분석하여 티켓 생성 필요성을 판단합니다.
        Args:
            thread_context: 스레드 전체 대화문맥(문자열)
        Returns:
            분석 결과 딕셔너리
        """
        try:
            prompt_path = os.path.join(BASE_DIR, 'prompts', 'thread_system_prompt.txt')
            with open(prompt_path, 'r', encoding='utf-8') as f:
                thread_system_prompt = f.read()
            prompt = thread_context
            response = self.client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": thread_system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            content = response.choices[0].message.content
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_str = content[start:end].strip()
            else:
                json_str = content.strip()
            result = json.loads(json_str)
            logger.info(f"OpenAI thread analysis result: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to analyze thread context with OpenAI: {e}\n{thread_context}\n{traceback.format_exc()}")
            return None

def build_prompt(messages: List[Dict], system_prompt: str, recent_tickets: List[Dict]) -> str:
    joined = '\n'.join([f"[{m['user']}] {m['text']}" for m in messages])
    recent_ticket_lines = '\n'.join([
        f"- [{t['key']}] {t['summary']}" for t in recent_tickets if t['summary']
    ])
    duplicate_guideline = (
        "\n## 최근 생성된 티켓 목록\n"
        f"{recent_ticket_lines}\n"
        "\n## 지침\n"
        "- 최근 티켓과 유사한 내용이면 중복 티켓을 생성하지 마세요.\n"
        "- 중복 여부를 판단해 'is_duplicate': true/false, 'duplicate_reason': '...' 필드를 반드시 포함하세요.\n"
    )
    return f"{system_prompt}\n{duplicate_guideline}\n---\n{joined}\n---\n티켓으로 생성할 메시지만 JSON 배열로 반환하세요."

def parse_response(response_text: str) -> List[Dict]:
    try:
        # 코드블록(```json ... ```) 제거
        if response_text.strip().startswith("```"):
            start = response_text.find("```") + 3
            if response_text[start:start+4] == "json":
                start += 4
            end = response_text.rfind("```")
            response_text = response_text[start:end].strip()
        return json.loads(response_text)
    except Exception:
        return []

def classify_messages(messages: List[Dict], system_prompt: str, recent_tickets: List[Dict]) -> List[Dict]:
    prompt = build_prompt(messages, system_prompt, recent_tickets)
    logger = logging.getLogger(__name__)
    logger.info(f"OpenAI 프롬프트: {prompt}")
    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1024,
            temperature=0.5
        )
        response_text = completion.choices[0].message.content
        logger.info(f"OpenAI 응답: {response_text}")
        return parse_response(response_text)
    except Exception as e:
        logger.error(f"OpenAI API 호출 실패: {e}")
        return []
