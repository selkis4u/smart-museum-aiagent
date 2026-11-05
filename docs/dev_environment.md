# 개발 환경

작성일 2026-11-05. 세 모듈 모두 시연 노트북 한 대(Windows, RAM 16GB, GPU 없음)에서 돌기 때문에(인터페이스 명세 0장) 같은 기준으로 맞춥니다.

## 1. 공통

| 항목 | 사용 | 비고 |
|---|---|---|
| OS | Windows 10/11 | 시연 노트북 |
| 언어 | Python 3.11.9 | 설치할 때 "Add Python to PATH" 체크 |
| 가상 환경 | `venv` | 모듈별로 따로 만듦(2장) |
| IDE | PyCharm Community | 인터프리터를 각 가상 환경의 `python.exe`로 지정. VS Code도 가능 |
| 형상 관리 | Git, GitHub (`selkis4u/smart-museum-aiagent`) | |
| 비밀 값 | `.env` + `python-dotenv` | API 키·DB 비밀번호는 저장소에 올리지 않음(NFR-11) |

## 2. 가상 환경

모듈마다 가상 환경을 따로 만듭니다. Agent는 torch·ChromaDB처럼 큰 패키지를 쓰고 Web은 학원 실습 버전을 그대로 쓰므로, 한 환경에 넣으면 버전이 서로 부딪칠 수 있습니다.

| 모듈 | 가상 환경 | 패키지 목록 |
|---|---|---|
| Web (Flask) | `venvs\web` | `web/requirements.txt` |
| Agent | `venvs\agent` | `agent/retrieval/requirements.txt`, `agent/knowledge/requirements.txt` |
| CV | `venvs\cv` | `cv/requirements.txt` |

```bat
python -m venv C:\venvs\web
C:\venvs\web\Scripts\activate
pip install -r web\requirements.txt
```

## 3. Web (Flask)

학원 실습 "설치 버전들(final)" 기준입니다. 실제 설치된 값은 가상 환경에서 `pip freeze > web\requirements.txt`로 남깁니다.

| 패키지 | 버전 | 용도 |
|---|---|---|
| Flask | 3.0.3 | 웹 서버, 도구용 API |
| Jinja2 · Werkzeug · itsdangerous · MarkupSafe | 3.1.4 · 3.0.3 · 2.2.0 · 3.0.2 | Flask 기본 구성 |
| Flask-SQLAlchemy · SQLAlchemy | 3.1.1 · 2.0.21 | ORM |
| Flask-Migrate · alembic | 4.0.7 · 1.11.1 | |
| Flask-WTF · email_validator | 1.2.2 · | 관리자 로그인·유물 정보 입력 폼 |
| Flask-Cors | 4.0.1 | |
| python-dotenv | 1.0.1 | `.env` 읽기 |
| dnspython · idna | 2.6.1 · 3.7 | email_validator 의존 패키지 |

목록에 없지만 이 프로젝트에 더 필요한 것:

| 패키지 | 용도 | 근거 |
|---|---|---|
| `oracledb` (python-oracledb) | Oracle 접속 드라이버. thin 모드라 Instant Client 불필요 |  |
| Flask-SocketIO | CV 좌표 수신(`/cv`), 브라우저 갱신(`/admin`) | 인터페이스 명세 0장 |

실행은 다음과 같습니다.

```bat
set FLASK_APP=<앱 이름>
set FLASK_DEBUG=1
flask run
```

포트는 5000입니다(인터페이스 명세 0장).

## 4. DB (Oracle)

| 항목 | 사용 | 비고 |
|---|---|---|
| DBMS | Oracle Database 18c Express Edition (XE) | 무료, CPU 2스레드·메모리 2GB·데이터 12GB 제한 |
| 접속 서비스 | `XEPDB1` (플러거블 DB) | `localhost:1521/XEPDB1` |
| 관리 도구 | Oracle SQL Developer 19 이상 (JDK 11 필요) | **테이블 생성**, 데이터 확인, 쿼리 실행 |
| 프로젝트 계정 | 전용 계정(예: `museum`) | 실습 계정(scott·hr)과 섞지 않음 |
| 설계 문서 | `docs/design/db/` | ERD, DDL, 통계 쿼리, Oracle 주의점 |

**프로젝트 계정 만들기** (SQL Developer 또는 sqlplus에서 `system`으로 접속)

```sql
ALTER SESSION SET CONTAINER = XEPDB1;
CREATE USER museum IDENTIFIED BY <비밀번호>;
GRANT CONNECT, RESOURCE, UNLIMITED TABLESPACE TO museum;
```

`XEPDB1` 안에 만들면 실습 때 쓴 `_ORACLE_SCRIPT` 설정 없이 일반 계정을 만들 수 있습니다.

**테이블 만들기**: 위 계정으로 SQL Developer에 접속해 `docs/design/db/schema_draft.sql`을 스크립트 실행(F5)합니다. Flask는 이 테이블에 연결만 합니다(`docs/design/db/README.md` 6장).

**Flask 접속 설정** (`config.py`, 비밀번호는 `.env`)

```python
SQLALCHEMY_DATABASE_URI = (
    f"oracle+oracledb://museum:{os.environ['ORACLE_PASSWORD']}@localhost:1521/?service_name=XEPDB1"
)
```

## 5. Agent

| 항목 | 사용 |
|---|---|
| 패키지 | `agent/retrieval/requirements.txt` (openai, chromadb, rank_bm25, kiwipiepy, sentence-transformers 등) |
| 외부 API | OpenAI(임베딩·생성), e뮤지엄 공공데이터 API. 키는 각 폴더 `.env` |
| 모델 | 임베딩 `text-embedding-3-small`, Re-ranker `BAAI/bge-reranker-v2-m3`(CPU) |
| 실행 방법 | `agent/retrieval/README.md` |

## 6. 버전을 바꿀 때

- 버전과 다르게 올려야 하면 팀에 알리고 `requirements.txt`를 같이 고칩니다.
- 새 PC에 설치할 때는 2장 순서대로 가상 환경을 만들고 `pip install -r ...`만 하면 같은 환경이 됩니다.
