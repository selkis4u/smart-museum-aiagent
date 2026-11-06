# 스마트 박물관을 위한 Physical AI 유물 보호·도슨트 서비스

유물 보호를 위해 보고(Vision), 판단하고(AI Agent), 행동하는 Physical AI Robot

1차(2026-11-02 ~ 12-04)는 CCTV로 유물 접근을 보고(Vision) AI Agent가 상황을 판단해 조명·음성 경고와 도슨트 해설을 실시간으로 제어합니다. 2차(2027-01-18 ~ 02-28 예정)는 같은 판단을 Physical AI Robot의 차단·수거·안내 동작으로 넓힙니다.

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
