# Tech Watch Tracker

경쟁사 릴리즈와 기술 트렌드를 자동으로 수집하고, AI 요약과 Discord 알림으로 
팀의 전략 리서치 업무를 자동화한 로컬 웹 대시보드입니다.

## 만든 이유

전략 기획 업무에서 경쟁사 동향과 기술 트렌드를 매일 수동으로 검색하고 
정리하는 반복 작업이 있었습니다. 시간 소모가 크고, 정보가 개인에게만 남는 
구조가 문제였습니다.

이 문제를 직접 정의하고, Codex를 활용해 자동화 도구를 만들었습니다.
코딩 경험 없이 문제 정의와 설계에 집중해 구현한 프로젝트입니다.

## 주요 기능

- 경쟁사 릴리즈 및 기술 키워드 뉴스 자동 수집 (RSS/Atom 피드)
- Gemini AI 기반 자동 요약 (전략적 관점)
- 새 정보 수집 시 Discord 자동 알림
- 주간/월간 전략 보고서 자동 생성
- 프로필 기반 운영 (개인 관심사 분리 + 팀 자산 중앙 축적)
- AI 활용 키워드 추천 

## 구현 방식

| 항목 | 내용 |
|---|---|
| 구현 방법 | ChatGPT Codex를 활용한 AI 코딩 |
| 나의 역할 | 문제 정의, 요구사항 설계, 기능 구성 기획, 결과물 검증 |
| 직접 작성한 코드 | 없음 |
| 형상관리 | Git, GitHub |

## 기술 스택(Codex 구현)

- Frontend: HTML, CSS, JavaScript
- Backend: Python, FastAPI
- Database: SQLite
- AI: Gemini API
- 알림: Discord Webhook

## 실행 방법

1. `config.example.json`을 복사해 `config.json`으로 저장합니다.
2. `config.json`에 API Key와 Discord Webhook을 입력합니다.
3. 아래 명령어로 실행합니다.

```bash
python3 web_server.py
```

4. 브라우저에서 `http://localhost:8000`으로 접속합니다.

## 보안 안내

`config.json`과 데이터베이스 파일은 `.gitignore`에 포함되어 
GitHub에 올라가지 않습니다.
