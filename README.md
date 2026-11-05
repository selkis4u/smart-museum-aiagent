# smart-museum-ai-agent
스마트 박물관 AI Agent로 전시유물을 보고 관람객을 판단하여 도슨트를 실시간 생성합니다.

## 폴더 구조

```
smart-museum-ai-agent/
├── CONTEXT.md          # 도메인 용어집 (도슨트 세션, 침범, 해제 등)
├── docs/
│   ├── dev_environment.md  # 개발 환경 (Python·Flask·Oracle 버전, 가상 환경)
│   ├── adr/            # 설계 결정 기록 (Architecture Decision Records)
│   ├── interface/      # 모듈 간 인터페이스 명세
│   └── requirements/   # 요구사항 분석서·명세서
├── cv/                 # Computer Vision (김수환)
├── agent/              # Agentic AI (송용석)
└── web/                # Web Service (김재원)
```

## 개발 환경

| 구분 | 사용 |
| --- | --- |
| 언어·도구 | Python 3.11.9, 가상 환경(venv, 모듈별), PyCharm Community, Git·GitHub |
| Web | Flask 3.0.3, Flask-SQLAlchemy 3.1.1, Flask-WTF, Flask-SocketIO |
| DB | Oracle Database 18c XE, Oracle SQL Developer(테이블 생성·관리), python-oracledb |
| Agent | LangGraph, OpenAI API, ChromaDB, BM25(kiwi), bge-reranker-v2-m3 |

자세한 버전과 설치 순서는 [`docs/dev_environment.md`](docs/dev_environment.md)를 봅니다.

## 1차 개발 일정 (2026-11-02 ~ 2026-12-04)

| 주차 | 내용 |
| --- | --- |
| 1주차 | 요구사항 명세서·분석서 |
| 2주차 | 화면 설계 및 UML 설계 |
| 3~4주차 | 개발 |
| 5주차 | 통합 테스트 및 자료 정리 |
