-- 스마트박물관 AI Agent RDB 스키마 초안 (Agent 제안, Web 확정)
-- 근거: 인터페이스 명세 4.4 기록 저장 API, 8장 유물 기본 정보, 요구사항 FR-WEB-01·02·08·09·10·11·14
-- SQLite 기준. MySQL로 옮길 때: INTEGER PRIMARY KEY AUTOINCREMENT → INT AUTO_INCREMENT PRIMARY KEY,
--   TEXT(JSON) → JSON, DATETIME → DATETIME(3), BOOLEAN은 그대로(TINYINT(1)).
-- 시각은 한국 시각(+09:00)을 오프셋 없이 'YYYY-MM-DD HH:MM:SS.SSS'로 저장한다(설계 문서 5장 참고).

-- FR-WEB-01 관리자 로그인(단일 계정)
CREATE TABLE admin_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,              -- werkzeug.security.generate_password_hash
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- FR-WEB-02 유물 정보. 초기 데이터 docs/interface/samples/artifacts_seed.json
CREATE TABLE artifacts (
    artifact_id   VARCHAR(10)  PRIMARY KEY,           -- A001 (세 모듈 공통 키)
    collection_no VARCHAR(30)  NOT NULL UNIQUE,       -- 소장품 번호 본관9663
    emuseum_id    VARCHAR(30)  UNIQUE,
    name          VARCHAR(100) NOT NULL,              -- 화면 표시 이름
    name_official VARCHAR(255),                       -- e뮤지엄 공식 명칭
    era           VARCHAR(30),                        -- 시대 신라·조선·고려
    era_detail    VARCHAR(50),                        -- 1622년, 15~16세기경
    museum        VARCHAR(100) NOT NULL,              -- 소장처
    designation   VARCHAR(30),                        -- 국보·보물
    material      VARCHAR(100),
    size          VARCHAR(100),
    author        VARCHAR(100),
    description   TEXT,
    display_kind  VARCHAR(10)  NOT NULL CHECK (display_kind IN ('SHOWCASE','OPEN','WALL')),
    role          VARCHAR(10)  NOT NULL CHECK (role IN ('DEMO','SPARE')),
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A002 복장물처럼 따로 등록하지 않는 부속 소장품(조회 화면 참고 정보)
CREATE TABLE artifact_related_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id   VARCHAR(10)  NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    collection_no VARCHAR(30)  NOT NULL UNIQUE,
    emuseum_id    VARCHAR(30),
    name          VARCHAR(255) NOT NULL,
    designation   VARCHAR(30)
);

-- FR-WEB-08 침범 기록. POST로 열고 PATCH로 갱신·닫음(명세 4.4)
CREATE TABLE intrusion_records (
    record_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id         VARCHAR(40)  NOT NULL UNIQUE,    -- 연 이벤트(evt-… 또는 sync-…). 같은 값이 다시 오면 기존 record_id 반환
    zone_id          VARCHAR(10)  NOT NULL,
    artifact_id      VARCHAR(10)  NOT NULL REFERENCES artifacts(artifact_id),  -- 침범 당시 유물(교체돼도 기록은 유지)
    start_level      VARCHAR(10)  NOT NULL CHECK (start_level IN ('CAUTION','WARNING')),
    max_level        VARCHAR(10)  NOT NULL CHECK (max_level IN ('CAUTION','WARNING')),
    cause            VARCHAR(20)  CHECK (cause IN ('LINE_1','LINE_2','TOUCH','CAUTION_TIMEOUT')),  -- 마지막으로 단계를 올린 원인, 동기화 기록은 NULL
    visitor_ids      TEXT         NOT NULL DEFAULT '[]',  -- JSON 정수 배열, 닫을 때 침범자 전원으로 바뀜
    started_at       DATETIME     NOT NULL,           -- CV 이벤트 timestamp
    ended_at         DATETIME,                        -- NULL = "종료 미확인"
    duration_ms      INTEGER,                         -- 닫을 때 Flask가 계산
    session_id       VARCHAR(40),                     -- 당시 세션(세션 기록은 끝날 때 생기므로 FK 아님)
    session_paused   BOOLEAN      NOT NULL DEFAULT 0,
    repeated_caution BOOLEAN      NOT NULL DEFAULT 0,
    last_event_id    VARCHAR(40),                     -- 마지막 PATCH의 event_id(재시도 중복 확인용)
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_intrusion_artifact_started ON intrusion_records (artifact_id, started_at);
CREATE INDEX ix_intrusion_started ON intrusion_records (started_at);

-- FR-WEB-09 세션 기록. 세션이 끝날 때 한 번 POST(명세 4.4)
CREATE TABLE docent_sessions (
    session_id        VARCHAR(40)  PRIMARY KEY,       -- ses-Z01-20261120-140300000
    zone_id           VARCHAR(10)  NOT NULL,
    artifact_id       VARCHAR(10)  NOT NULL REFERENCES artifacts(artifact_id),
    started_at        DATETIME     NOT NULL,
    ended_at          DATETIME     NOT NULL,
    end_reason        VARCHAR(30)  NOT NULL CHECK (end_reason IN
                        ('LEFT_AFTER_COMPLETE','LEFT_DURING_NARRATION','LEFT_WHILE_PAUSED',
                         'LEFT_WHILE_SPEAKER_WAIT','NEW_SESSION')),
    start_count       INTEGER      NOT NULL,          -- 시작 인원
    script_end_count  INTEGER      NOT NULL DEFAULT 0,-- 원고 끝 시점 인원
    completed_count   INTEGER      NOT NULL DEFAULT 0,-- 끝까지 들은 인원
    script            TEXT,                           -- 생성 원고(대체 해설이면 그 원고)
    rag_chunk_ids     TEXT         NOT NULL DEFAULT '[]',  -- JSON 문자열 배열
    source_urls       TEXT         NOT NULL DEFAULT '[]',  -- JSON 문자열 배열
    fallback_used     BOOLEAN      NOT NULL DEFAULT 0,
    generation_failed BOOLEAN      NOT NULL DEFAULT 0,-- 해설 도중 생성 실패(명세 7장 안건 10)
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_session_artifact_started ON docent_sessions (artifact_id, started_at);

-- FR-WEB-14 규칙 위반 기록
CREATE TABLE violation_records (
    record_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     VARCHAR(40)  NOT NULL UNIQUE,
    zone_id      VARCHAR(10)  NOT NULL,
    artifact_id  VARCHAR(10)  NOT NULL REFERENCES artifacts(artifact_id),
    visitor_id   INTEGER      NOT NULL,
    item_type    VARCHAR(20)  NOT NULL CHECK (item_type IN ('TAKEOUT_CUP')),
    occurred_at  DATETIME     NOT NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_violation_artifact_occurred ON violation_records (artifact_id, occurred_at);
