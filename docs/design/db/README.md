# RDB 설계 초안 (Agent 제안, Web 확정)

작성일 2026-11-05, 수정 2026-11-05(Oracle로 변경). 작성 송용석(Agent), 확정 김재원(Web). 인터페이스 명세(`docs/interface/interface_spec_v0.1.md`) 4.4 기록 저장 API와 8장 유물 기본 정보를 그대로 받을 수 있게 짠 제안안입니다. 테이블 이름과 타입은 Web에서 바꿔도 되고, **API로 들어오는 필드 이름과 열거값만 명세와 맞으면 됩니다.**

**DB는 Oracle 하나로 씁니다.** 개발과 시연 모두 Oracle이고, SQLite 같은 다른 DB를 섞지 않습니다.

| 파일 | 내용 |
|---|---|
| `schema_draft.sql` | 테이블 6개 Oracle DDL |
| `stats_queries.sql` | FR-WEB-11 통계표 쿼리 예시 5개 (Oracle) |
| `check_oracle.py` | 위 두 파일을 Oracle에서 실제로 돌려 보는 검증 스크립트 |
| `../../interface/samples/artifacts_seed.json` | 유물 4점 초기 데이터(명세 8장) |

**확인한 것** (Oracle Database Free 23ai, `python-oracledb` thin 모드, `check_oracle.py`)
- DDL 11문 실행, 유물 4점과 부속 소장품 3건 입력
- 가짜 이벤트 시나리오(`docs/interface/samples/cv_events_scenario.jsonl`)로 만든 침범 기록을 열기·갱신·닫기. 지속 시간 10,777ms가 밀리초까지 맞음
- 다섯 가지가 제약으로 막힘: 중복 `event_id`, 등록되지 않은 유물, 틀린 종료 사유, JSON이 아닌 `visitor_ids`, 빈 문자열 이름
- 한글 100자 이름과 긴 원고(CLOB) 저장
- 통계 쿼리 5개 결과가 손으로 센 값과 같음

## 1. ERD

```mermaid
erDiagram
    artifacts ||--o{ artifact_related_items : "부속 소장품"
    artifacts ||--o{ intrusion_records : "침범 당시 유물"
    artifacts ||--o{ docent_sessions : "세션 유물"
    artifacts ||--o{ violation_records : "위반 당시 유물"
    docent_sessions |o..o{ intrusion_records : "session_id (FK 아님)"

    admin_users {
        number id PK
        varchar2 username UK
        varchar2 password_hash
    }
    artifacts {
        varchar2 artifact_id PK "A001"
        varchar2 collection_no UK "본관9663"
        varchar2 emuseum_id UK
        varchar2 name
        varchar2 era
        varchar2 era_detail
        varchar2 museum
        varchar2 designation
        varchar2 material
        varchar2 size_info
        clob description
        varchar2 display_kind "SHOWCASE OPEN WALL"
        varchar2 role "DEMO SPARE"
    }
    artifact_related_items {
        number id PK
        varchar2 artifact_id FK
        varchar2 collection_no UK
        varchar2 name
    }
    intrusion_records {
        number record_id PK
        varchar2 event_id UK
        varchar2 zone_id
        varchar2 artifact_id FK
        varchar2 start_level
        varchar2 max_level
        varchar2 cause
        clob visitor_ids "JSON"
        timestamp started_at
        timestamp ended_at "NULL=종료 미확인"
        number duration_ms
        varchar2 session_id
        number session_paused "0/1"
        number repeated_caution "0/1"
    }
    docent_sessions {
        varchar2 session_id PK
        varchar2 zone_id
        varchar2 artifact_id FK
        timestamp started_at
        timestamp ended_at
        varchar2 end_reason
        number start_count
        number script_end_count
        number completed_count
        clob script
        clob rag_chunk_ids "JSON"
        clob source_urls "JSON"
        number fallback_used "0/1"
        number generation_failed "0/1"
    }
    violation_records {
        number record_id PK
        varchar2 event_id UK
        varchar2 zone_id
        varchar2 artifact_id FK
        number visitor_id
        varchar2 item_type
        timestamp occurred_at
    }
```

## 2. 테이블과 요구사항

| 테이블 | 요구사항 | 채우는 곳 |
|---|---|---|
| `admin_users` | FR-WEB-01 관리자 로그인(단일 계정) | Web 초기 설정 |
| `artifacts`, `artifact_related_items` | FR-WEB-02 유물 정보 관리 | `artifacts_seed.json`으로 초기 등록 후 관리 화면에서 수정 |
| `intrusion_records` | FR-WEB-08 침범 기록 | Agent `POST/PATCH /api/records/intrusions` |
| `docent_sessions` | FR-WEB-09 세션 기록 | Agent `POST /api/records/sessions` |
| `violation_records` | FR-WEB-14 규칙 위반 기록 | Agent `POST /api/records/violations` |

조회(FR-WEB-10)는 세 기록 테이블을 기간·유물·위험 단계로 거르고, 통계(FR-WEB-11·15)는 `stats_queries.sql`처럼 집계만 합니다. 통계용 테이블은 따로 두지 않습니다.

## 3. API 필드 → 열

**유물 초기 데이터**: JSON의 `size`는 `size_info` 열에 넣습니다(`SIZE`는 Oracle 예약어). `related_items`는 `artifact_related_items`에 한 줄씩 넣습니다. 나머지 필드는 같은 이름의 열에 넣습니다.

**침범 기록**
- `POST`: `level` → `start_level`과 `max_level` 둘 다에 넣습니다. 나머지 필드는 같은 이름의 열에 넣습니다. 같은 `event_id`가 다시 오면 새로 만들지 않고 기존 `record_id`를 돌려줍니다(명세 1장 재시도 규칙).
- `PATCH` 갱신(`max_level`·`cause`·`visitor_ids`): 값을 덮어쓰고, 요청의 `event_id`를 `last_event_id`에 남깁니다. 같은 값을 다시 덮어쓰는 것이라 재시도가 와도 결과가 같습니다.
- `PATCH` 닫기(`ended_at`·`visitor_ids`): `duration_ms`를 Flask가 Python에서 계산합니다(`(ended_at - started_at).total_seconds() * 1000`). `ended_at`이 NULL이면 화면에 "종료 미확인"으로 표시합니다.
- `start_level`은 명세에 없는 열입니다. API는 바꾸지 않고, 열 때 받은 `level`을 따로 남겨서 "주의로 시작해 경고로 오른 침범"과 "처음부터 경고"(2차 안전선·접촉 시도)를 구분합니다.

**세션 기록**: 명세 4.4 필드를 같은 이름의 열에 넣습니다. 배열(`rag_chunk_ids`·`source_urls`)은 JSON 문자열로, `true/false`는 1/0으로 넣습니다. `generation_failed`는 명세 7장 안건 10에 따라 추가합니다.

**규칙 위반 기록**: 명세 4.4 필드를 같은 이름의 열에 넣습니다.

## 4. Oracle에서 꼭 지킬 것

검증하면서 실제로 확인한 함정입니다.

1. **밀리초가 사라지지 않게 `TIMESTAMP`로 보내기.** `python-oracledb`는 Python `datetime`을 기본으로 `DATE` 형식으로 보내서 밀리초를 버립니다(검증에서 10.777초가 10.900초로 나옴). 지연 측정(NFR-02)과 지속 시간에 밀리초가 필요합니다.
   - Flask-SQLAlchemy: 열 타입을 `db.DateTime`이 아니라 **`db.TIMESTAMP`**로 선언합니다. Oracle에서 `DateTime`은 `DATE` 열로 만들어지고 값도 밀리초를 버리며, `TIMESTAMP`는 남는 것을 확인했습니다.
   - `oracledb`를 직접 쓸 때: 연결에 입력 타입 처리기를 답니다(`check_oracle.py`의 `ts_handler` 참고).
2. **빈 문자열은 NULL입니다.** Oracle은 `''`을 NULL로 저장해서 `NOT NULL` 열에 넣으면 `ORA-01400` 오류가 납니다. 관리 화면에서 빈 입력은 검사해서 막거나, 선택 항목이면 `None`으로 넣습니다.
3. **문자열 길이는 글자 수(`CHAR`)로.** DDL은 모두 `VARCHAR2(n CHAR)`입니다. `CHAR`를 빼면 바이트 단위가 되어, 한글(UTF-8 3바이트)은 n/3자밖에 안 들어갑니다. SQL Developer에서 직접 테이블을 만들 때 특히 주의합니다. SQLAlchemy의 `db.String(100)`은 `VARCHAR2(100 CHAR)`로 만들어지는 것을 확인했습니다.
4. **시각은 오프셋 없는 한국 시각으로 저장합니다.** API는 `+09:00`이 붙은 ISO 문자열로 오가므로, Flask에서 받을 때 오프셋을 떼어 `datetime`으로 바꾸고, 내보낼 때 다시 붙입니다. 세 모듈이 한 PC에서 돌아서(명세 0장) 시간대를 따로 다룰 필요가 없습니다. 시간대 통계는 `TO_CHAR(started_at, 'HH24')`로 그대로 한국 시각 기준입니다.
5. **GROUP BY에는 SELECT의 일반 열을 모두 적습니다.** Oracle은 별칭으로 GROUP BY 할 수 없고, 빠진 열이 있으면 오류가 납니다(`stats_queries.sql` 참고).

## 5. 설계 선택

- **구역 테이블을 두지 않습니다.** 구역·안전선·스피커는 공간 설정 파일(`config/space.json`)이 유일한 원본이고 Web은 조회만 합니다(FR-WEB-02, 명세 5장). 기록에는 `zone_id`를 값으로만 남깁니다.
- **기록에 `artifact_id`를 직접 남깁니다.** 유물을 교체하면(S14) 같은 `Z01`이라도 유물이 바뀌므로, 기록 당시의 유물을 남겨야 통계가 맞습니다.
- **`intrusion_records.session_id`는 FK가 아닙니다.** 세션 기록은 세션이 끝날 때 한 번 저장되므로, 침범 기록을 열 때는 아직 세션 행이 없습니다. 조회할 때 LEFT JOIN으로 붙입니다.
- **배열은 JSON 열(`CLOB` + `IS JSON` 검사)에 둡니다.** `visitor_ids`·`rag_chunk_ids`·`source_urls`는 보여 주기만 하고 집계에 쓰지 않으므로 별도 테이블로 나누지 않습니다. 2차에서 "관람객별 침범 이력" 같은 조회가 필요하면 그때 나눕니다.
- **참/거짓은 `NUMBER(1)` 0/1입니다.** 23ai는 `BOOLEAN`도 되지만, 학원이나 다른 PC에 설치된 Oracle 버전이 낮아도 그대로 돌게 하기 위해서입니다.
- 동기화로 연 침범 기록(`event_id`가 `sync-…`, `cause` NULL)도 같은 테이블에 들어갑니다(명세 4.4).

## 6. 설치와 검증 (시연 노트북)

- 학원 실습에서 설치한 **Oracle Database 18c XE**를 씁니다(설치·계정 만들기는 `docs/dev_environment.md` 4장). CPU 2스레드, 메모리 2GB, 데이터 12GB 제한이 있어서 같은 노트북의 CV(YOLO)와 Re-ranker 자원을 많이 쓰지 않습니다. 시연 데이터는 기록 수백 건이라 용량도 충분합니다. DDL은 12c 이상 문법만 써서 18c XE에서도 돌아가야 하지만, 이 문서의 실행 확인은 Oracle Database Free 23ai에서 했으므로 18c XE에서 `check_oracle.py`로 한 번 다시 확인합니다.
- Python은 **`python-oracledb`** thin 모드를 씁니다. Instant Client를 따로 설치하지 않아도 됩니다. SQLAlchemy 접속 주소는 `oracle+oracledb://<계정>:<비밀번호>@localhost:1521/?service_name=XEPDB1`입니다. 비밀번호는 저장소에 올리지 말고 `.env`에 둡니다(NFR-11).
- **테이블은 Oracle SQL Developer로 만듭니다 [11/5 결정].** 계정으로 접속 → `schema_draft.sql` 내용을 워크시트에 붙여 넣기 → **스크립트 실행(F5)**. F5는 여러 문장을 차례로 실행하고, Ctrl+Enter(명령문 실행)는 커서가 있는 한 문장만 실행합니다. 만든 뒤 왼쪽 접속 트리의 "테이블"에서 6개를 확인하고, 통계 쿼리는 `stats_queries.sql`의 SELECT를 하나씩 Ctrl+Enter로 돌려 봅니다.
- **Flask는 만들어진 테이블에 연결만 합니다.** Flask-SQLAlchemy 모델은 `schema_draft.sql`과 같은 열 이름·타입으로 쓰고, `flask db migrate`·`flask db upgrade`(Flask-Migrate)나 `db.create_all()`로 테이블을 만들지 않습니다. 두 곳에서 테이블을 만들면 정의가 어긋나기 때문입니다. 테이블을 바꿀 때는 `schema_draft.sql`을 먼저 고치고 SQL Developer에서 `ALTER TABLE`로 반영한 뒤 모델을 맞춥니다.
- 모델을 쓸 때도 4장 1번(시각은 `db.TIMESTAMP`)과 2번(빈 문자열)은 지켜야 합니다.
- 테이블을 만든 뒤 빈 검증용 계정에서 `python docs/design/db/check_oracle.py`로 한 번 확인합니다(실행 방법은 파일 머리말). 이 스크립트는 같은 이름의 테이블을 지우고 다시 만들므로 시연용 계정에는 돌리지 않습니다.

## 7. Web 확인 요청

1. Oracle 18c XE 사용과, 테이블은 SQL Developer로 만들고 Flask는 연결만 하는 방식(6장)
2. 시각 저장 방식(4장 4번): 오프셋을 떼어 저장하는 방식에 동의하는지
3. `start_level` 열 추가(API 변경 없음)와 `size` → `size_info` 이름 변경에 동의하는지
4. 명세 7장 안건 10 `generation_failed` 필드 추가
