from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

_SYSTEM_INSTRUCTION = """당신은 헬스장 상담 데이터 분석 전문가입니다.
예약관리 시트의 행 데이터를 분석해 신규DB 시트 입력값을 JSON으로 반환합니다.
반드시 JSON만 반환하고 다른 텍스트는 절대 포함하지 마세요.

[상담 방식 분류 기준]
- 씹힘, 부재중, 연락 안됨, 전화 안받음, 부재 -> "부재"
- 전화, 통화, 유선, 전화로 -> "유선"
- 방문, 대면, 오셔서, 내방, 와서, 직접 -> "대면"
- 네이버, 톡톡, 문의, 카톡, 인스타, 온라인 -> "인터넷"
- 위 키워드가 없으면 문맥에서 유추

[날짜 파싱 규칙]
내용의 0703) 형식 → "07/03" 으로 변환
날짜가 없는 상담은 예약일을 사용

[응답 JSON 스키마 — 이 구조 그대로 반환]
{
  "파트": "string",
  "유형": "string",
  "날짜": "MM/DD",
  "담당자": "string",
  "등록여부": "string",
  "이름": "string",
  "연락처": "string",
  "방문날짜": "MM/DD or empty",
  "방문시간": "string",
  "성별": "string",
  "연령대": "string",
  "관심종목": "string",
  "방문경로": "string",
  "등록종목": "string",
  "등록기간": "string",
  "구분": "신규 or 재등",
  "상담내역": [
    {
      "상담자": "string",
      "날짜": "MM/DD",
      "방식": "부재 or 유선 or 대면 or 인터넷",
      "내용": "string"
    }
  ]
}"""


def analyze_consultation(api_key: str, row_data: dict, defaults: dict) -> dict:
    """Gemini API로 상담 행 데이터를 분석해 신규DB 입력값 dict를 반환한다."""
    user_text = (
        f"아래 상담 데이터를 분석해서 신규DB 입력값 JSON을 반환하세요.\n\n"
        f"[상담 데이터]\n"
        f"성함: {row_data.get('name', '')}\n"
        f"전화번호: {row_data.get('phone', '')}\n"
        f"예약일: {row_data.get('reserved_date', '')}\n"
        f"방문예정일: {row_data.get('visit_date', '')}\n"
        f"종목: {row_data.get('category', '')}\n"
        f"금액: {row_data.get('amount', '')}\n"
        f"신규/재등: {row_data.get('is_new', '')}\n"
        f"내용:\n{row_data.get('notes', '')}\n\n"
        f"[기본값 - 데이터에서 알 수 없을 때 사용]\n"
        f"파트: {defaults.get('part', '실장')}\n"
        f"유형: {defaults.get('type', '워크인')}\n"
        f"담당자: {defaults.get('manager', '실장')}\n"
        f"상담자: {defaults.get('counselor', '실장')}"
    )

    payload = json.dumps({
        "system_instruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    url = f"{_API_URL}?key={api_key}"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini API 오류 ({e.code}): {e.read().decode('utf-8', errors='replace')}") from e

    text = body["candidates"][0]["content"]["parts"][0]["text"]
    # responseMimeType=json 이면 순수 JSON이지만, 방어적으로 마크다운 코드블록 제거
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)
