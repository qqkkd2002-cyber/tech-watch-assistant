# Tech Watch Tracker

Tech Watch Tracker는 경쟁사 릴리즈, RSS 피드, 키워드 뉴스를 수집하고 AI로 요약해 Discord와 웹 대시보드에서 확인할 수 있게 만든 로컬 웹앱입니다.

## 실행 방법

```bash
cd "/Users/parkjongho/Documents/New project/tech-watch-assistant"
python3 web_server.py
```

브라우저에서 아래 주소로 접속합니다.

```text
http://localhost:8000
```

## 설정 파일

실제 API Key, Discord Webhook, 관리자 비밀번호는 `config.json`에 넣습니다.

처음 세팅할 때는 아래처럼 샘플 파일을 복사해서 사용합니다.

```bash
cp config.example.json config.json
```

`config.json`은 `.gitignore`에 들어 있어 GitHub/GitLab에 올라가지 않습니다.

## Git에 올리면 안 되는 파일

- `config.json`: API Key, Discord Webhook 같은 비밀값
- `tech_watch.db`: 로컬 데이터베이스
- `*.log`, `*.err`: 실행 로그
- `__pycache__/`, `*.pyc`: 파이썬 임시 파일

## 기본 개발 흐름

1. 로컬 폴더에서 코드를 수정합니다.
2. `python3 web_server.py`로 실행해서 확인합니다.
3. 문제가 없으면 Git에 커밋합니다.
4. GitHub/GitLab 원격 저장소에 push합니다.
