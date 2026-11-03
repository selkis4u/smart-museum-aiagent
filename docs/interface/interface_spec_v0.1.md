# 인터페이스 명세 초안 v0.1

작성일 2026-11-03. 모듈 간 연결 형식 초안입니다. 6장 체크리스트 9개는 11/3에 결정했고(**[11/3 결정]** 표시), 나머지는 결정사항·명세서 v0.3을 그대로 옮긴 것이며 세부 형식은 추후 결정합니다. 확정되면 v1.0으로 올리고 각 모듈은 이 문서만 보고 가짜 데이터로 개발합니다(NFR-14).

## 0. 연결 구성

| 구간 | 방식 | 주소(예시, 설정 파일로 관리) | 서버 | 내용 |
|---|---|---|---|---|
| CV → Agent | WebSocket | `ws://127.0.0.1:8765/events` | Agent | 이벤트 DTO (변화가 있을 때만) |
| CV → Flask | Socket.IO 클라이언트 **[11/3 결정]** | `http://127.0.0.1:5000`, 네임스페이스 `/cv`, 이벤트 `coords` | Flask | 좌표 메시지 (초당 5회) |
| Agent → Flask | HTTP REST (JSON) | `http://127.0.0.1:5000/api/...` | Flask | MCP 도구가 부르는 도구용 API |
| Flask → 브라우저 | Socket.IO | 네임스페이스 `/admin` | Flask | 맵·구역 상태·알림 갱신 |

- CV → Flask를 Socket.IO로 추천하는 이유: Flask가 브라우저용으로 Flask-SocketIO를 이미 쓰므로 받은 좌표를 같은 서버에서 바로 브라우저로 넘길 수 있고, 연결을 유지해 초당 5회 전송에 요청마다 드는 비용이 없다. 단점은 CV가 Agent용 WebSocket 라이브러리와 별도로 python-socketio 클라이언트를 써야 하고, 서버와 클라이언트의 Socket.IO 버전을 맞춰야 한다는 것. 대안 HTTP POST 초당 5회는 가장 단순하고 curl·Postman으로 바로 시험할 수 있으며 부하도 문제없다. 연결 끊김 판정은 두 방식 모두 "3초 미수신"(FR-WEB-16)으로 같다. 지연 목표(NFR-04 0.5초)는 둘 다 충분히 맞출 수 있어 담당자가 편한 쪽으로 정해도 된다.
- **[11/3 결정] 재연결 주체**: Agent가 서버이므로 연결이 끊기면 클라이언트인 **CV가 5초 간격으로** 다시 연결한다(FR-WEB-16·결정사항 문구 정정). CV → Flask Socket.IO도 CV가 자동 재연결한다.
- **[11/3 결정] 실행 환경**: CV·Agent·Flask 세 모듈을 시연 노트북 한 대에서 실행한다. 주소는 모두 `127.0.0.1`, 포트는 Agent 8765·Flask 5000이며 `config/settings.yaml`에서 바꾼다. 시각은 한 PC의 시계를 쓰므로 시간 동기화는 필요 없다.
- **Agent 재접속 동기화**: CV 연결이 (다시) 맺어지거나 Agent가 재시작되면 Agent는 바로 `GET /api/zones/status`를 한 번 불러 구역별 현재 위험 단계를 맞춘다. CV는 끊긴 동안의 이벤트를 쌓아 두지 않는다(지난 이벤트는 의미가 없음).

## 1. 공통 규칙

- 인코딩 UTF-8 JSON, 필드 이름 `snake_case`, 열거값은 영어 대문자.
- 시각: ISO 8601, 밀리초와 +09:00 포함. 예 `2026-11-20T14:03:21.123+09:00`. 지연 측정(NFR-02·03·04)에 쓴다. 세 모듈이 한 PC에서 돌므로 같은 시계를 쓴다.
- 바닥 좌표: cm, 위에서 내려다본 평면. 원점은 캘리브레이션 기준점 P1, x축은 P1→P2 방향, y축은 P1→P4 방향. 화면 좌표: px, 원점 왼쪽 위.
- ID 형식

| ID | 형식 | 만드는 곳 |
|---|---|---|
| `artifact_id` | `A001` (1차 등록 유물 4점: 시연 `A001`·`A002`, 교체용 `A003`·`A004`. 혼동 테스트용 유사 유물 `D001`~`D011`은 Agent 지식 자료에만 있고 Web 등록·이벤트에는 나오지 않음) | Web 유물 등록 |
| `chunk_id` | e뮤지엄 자료 `A001-03`·`A002R1-03`(부속 소장품 접두어), PDF 자료 `GC2010-012` | Agent 지식 자료(`agent/knowledge/`) |
| `zone_id` | `Z01` | CV 설정 도구 |
| `visitor_id` | 정수 (트래커 ID) | CV |
| `event_id` | `evt-20261120-140321123-0001` (시각 + 일련번호, 재시작해도 겹치지 않음) | CV |
| `session_id` | `ses-Z01-20261120-140325123` | Agent |
| `record_id` | 정수 (DB 자동 증가) | Flask |
| `speaker_id` | `SPK1` | 공간 설정 파일 |

- 열거값

| 이름 | 값 |
|---|---|
| level | `NORMAL` `CAUTION` `WARNING` |
| cause | `LINE_1` `LINE_2` `TOUCH` `CAUTION_TIMEOUT` `CLEARED` |
| event type | `LEVEL_CHANGE` `VIEWING_START` `ZONE_EMPTY` `PROHIBITED_ITEM` |
| item_type | `TAKEOUT_CUP` |
| session state | `IDLE`(대기) `SPEAKER_WAIT`(스피커 대기) `NARRATING`(해설) `PAUSED`(일시정지) `RESUMING`(재개) `COMPLETED_WAIT`(완료 대기) `ENDED`(종료) |
| end reason | `LEFT_AFTER_COMPLETE`(완료 후 이탈) `LEFT_DURING_NARRATION`(해설 중 이탈) `LEFT_WHILE_PAUSED`(일시정지 중 이탈) `LEFT_WHILE_SPEAKER_WAIT`(스피커 대기 중 이탈) `NEW_SESSION`(새 세션 시작) |
| ment | `CAUTION` `WARNING` `NOTICE_PROHIBITED_ITEM` `BRIDGE_COMMON` |

- Flask 응답: 성공 `{"ok": true, ...}`, 실패는 HTTP 4xx/5xx와 `{"ok": false, "error": {"code": "ZONE_NOT_FOUND", "message": "..."}}`.
- 재시도와 중복: Agent는 도구 호출이 실패하면 1회 재시도한다(FR-WEB-16). 기록 저장 요청에는 `event_id`를 넣고 Flask는 같은 `event_id`가 이미 있으면 새로 만들지 않고 기존 결과를 돌려준다.
- 타임아웃(제안): 조명·음성 API 1초(NFR-02 1초 안에 들어오도록), 기록·상태 API 3초.

## 2. CV → Agent 이벤트 DTO

| 필드 | 타입 | 설명 |
|---|---|---|
| `type` | string | event type |
| `event_id` | string | 이벤트 고유 ID |
| `seq` | int | 연결마다 1부터 늘어나는 순번 **[11/3 결정]** 순서 확인·누락 확인용 |
| `zone_id` | string | |
| `artifact_id` | string | |
| `prev_level` / `level` | string | LEVEL_CHANGE가 아니면 둘 다 그 구역의 현재 단계 |
| `cause` | string \| null | LEVEL_CHANGE일 때만 |
| `visitor_ids` | int[] | LEVEL_CHANGE: 침범한 관람객, VIEWING_START: 판정 시점 구역 관람객, PROHIBITED_ITEM: 소지자 1명, ZONE_EMPTY: `[]` |
| `item_type` | string \| null | PROHIBITED_ITEM일 때만 |
| `timestamp` | string | 판정 시각(프레임 시각) |

```json
{"type":"LEVEL_CHANGE","event_id":"evt-20261120-140321123-0001","seq":41,"zone_id":"Z01","artifact_id":"A001",
 "prev_level":"NORMAL","level":"CAUTION","cause":"LINE_1","visitor_ids":[3],"item_type":null,
 "timestamp":"2026-11-20T14:03:21.123+09:00"}
```
```json
{"type":"PROHIBITED_ITEM","event_id":"evt-20261120-140400050-0002","seq":42,"zone_id":"Z02","artifact_id":"A002",
 "prev_level":"NORMAL","level":"NORMAL","cause":null,"visitor_ids":[7],"item_type":"TAKEOUT_CUP",
 "timestamp":"2026-11-20T14:04:00.050+09:00"}
```

- CAUTION_TIMEOUT(주의 5초 지속 → 경고)도 LEVEL_CHANGE로 보낸다. 단계가 같은 채로 원인만 바뀌는 경우(이미 경고인데 TOUCH)는 보내지 않는다.

## 3. CV → Flask 좌표 메시지 (초당 5회)

```json
{"type":"COORDS","frame":12345,"timestamp":"2026-11-20T14:03:21.200+09:00",
 "visitors":[
   {"visitor_id":3,"x":120.5,"y":340.2,"zone_id":"Z01","item_type":null},
   {"visitor_id":7,"x":410.0,"y":220.8,"zone_id":null,"item_type":"TAKEOUT_CUP"}],
 "zones":[
   {"zone_id":"Z01","level":"CAUTION","visitor_ids":[3]},
   {"zone_id":"Z02","level":"NORMAL","visitor_ids":[]}]}
```

- 감시 영역 밖 관람객은 보내지 않는다(좌표를 믿을 수 없음).
- `zone_id`는 그 관람객이 들어가 있는 도슨트 구역, 없으면 null(1차는 구역 겹침 금지라 하나뿐).
- `item_type`은 화면에 컵 소지자를 표시하는 데 쓴다 **[11/3 결정] 포함**.
- Flask는 마지막 메시지를 메모리에 두고 3초 넘게 안 오면 "CV 연결 끊김"(FR-WEB-16). NFR-04는 `timestamp`와 브라우저 표시 시각의 차이로 잰다.

## 4. 도구용 API (Agent MCP 도구 → Flask)

| MCP 도구 | 메서드·경로 | 관련 요구사항 |
|---|---|---|
| Vision 상황 조회 | `GET /api/zones/status` | FR-WEB-12, FR-AG-11·17 |
| 조명 제어 | `POST /api/light` | FR-WEB-06 |
| 음성 송출 | `POST /api/audio/narration` · `/notice` · `/priority` · `/stop` | FR-WEB-07 |
| 기록 저장 | `POST /api/records/intrusions`, `PATCH /api/records/intrusions/{record_id}`, `POST /api/records/sessions`, `POST /api/records/violations` | FR-WEB-08·09·14, FR-AG-18 |
| 상태 통지 | `POST /api/agent/state`, `POST /api/agent/heartbeat` | FR-WEB-04·16 |
| 지식 검색 | (Agent 내부, Flask API 아님) | FR-AG-02~06 |

### 4.1 상황 조회 `GET /api/zones/status`

좌표 메시지 최신값에 **구역별 재생 상태**를 함께 돌려준다. Agent는 해설·스피커 대기·완료 대기 동안 0.5초마다 불러 원고 재생이 끝난 시점과 스피커를 넘겨받은 시점을 안다 **[11/3 결정] Flask → Agent 재생 상태 전달은 이 조회 방식으로 한다** (Flask가 Agent에 이벤트를 보내는 방식은 연결이 하나 늘어나 쓰지 않음).

```json
{"ok":true,"cv_connected":true,"updated_at":"2026-11-20T14:03:21.200+09:00",
 "zones":[
   {"zone_id":"Z01","artifact_id":"A001","level":"CAUTION","visitor_ids":[3,5],"count":2,
    "audio":{"state":"PLAYING","session_id":"ses-Z01-20261120-140300000","sentence_no":4,
             "script_done_at":null}},
   {"zone_id":"Z02","artifact_id":"A002","level":"NORMAL","visitor_ids":[7],"count":1,
    "audio":{"state":"WAITING","session_id":"ses-Z02-20261120-140310000","sentence_no":null,
             "script_done_at":null}}]}
```

- `audio.state`: `IDLE`(소리 없음) `PLAYING`(이 구역 해설 재생 중) `WAITING`(스피커 차례 대기) `INTERRUPTED`(멘트 때문에 잠시 끊김).
- `script_done_at`: 원고 끝 표시(`is_last`) 문장의 재생이 끝난 시각. 완료 대기의 "해설 종료 10초 후" 기준.

### 4.2 조명 `POST /api/light`

```json
{"zone_id":"Z01","level":"CAUTION"}
```
응답 `{"ok":true}`. 웹 가상 조명 색: NORMAL 기본, CAUTION 노랑, WARNING 빨강.

### 4.3 음성 송출

| 동작 | 경로 | 요청 | 응답 |
|---|---|---|---|
| 해설 재생 | `POST /api/audio/narration` | `{"zone_id","session_id","sentence_no","kind":"SCRIPT"\|"BRIDGE","text"\|"audio_file","is_last"}` | `{"ok":true,"queue_length":3}` |
| 안내 재생 | `POST /api/audio/notice` | `{"zone_id","ment":"NOTICE_PROHIBITED_ITEM"}` | `{"ok":true}` |
| 우선 재생 | `POST /api/audio/priority` | `{"zone_id","ment":"CAUTION"\|"WARNING"}` | `{"ok":true,"interrupted":{"zone_id","session_id","sentence_no"}\|null}` |
| 정지 | `POST /api/audio/stop` | `{"zone_id"}` | `{"ok":true,"interrupted_sentence_no":4\|null,"cleared":3}` |

- `text`는 Flask가 edge-tts로 변환, `audio_file`은 미리 만든 파일(대체 해설·공통 연결 멘트)을 그대로 재생. 둘 중 하나만 보낸다.
- 연결 멘트는 `kind:"BRIDGE"`, `sentence_no`는 재개할 문장 번호와 같게 보내고 해설 문장보다 먼저 재생한다.
- `interrupted`가 다른 구역 문장이면 Flask가 멘트 뒤에 그 문장을 처음부터 다시 재생하므로 Agent는 무시한다. 같은 구역이면 그 `sentence_no`를 재개 위치로 저장한다.
- 돌려주는 문장 번호(우선 재생의 `interrupted.sentence_no`, 정지의 `interrupted_sentence_no`) 규칙:
  1. 재생 중이던 문장이 있으면 그 문장 번호
  2. 문장과 문장 사이라 재생 중인 문장이 없으면, 대기열에 남아 있던 아직 재생하지 않은 첫 문장 번호
  3. 재생 중인 문장도 대기열도 없을 때만 null
- Agent는 null을 받으면 앞서 저장한 재개 위치를 그대로 둔다(덮어쓰지 않음). 예: 주의로 이미 멈춘 상태에서 5초가 지나 경고로 올라가 우선 재생을 다시 부르면 끊을 해설이 없어 null이 온다.
- 응답 시점: Flask는 해설을 끊고 대기열을 비운 뒤 멘트 재생을 시작한 직후 응답한다. 멘트 재생이 끝날 때까지 기다리지 않는다(Agent의 조명·기록 호출이 늦어지지 않도록, NFR-02 1초).
- 정지는 그 구역 대기열만 비운다(반복 주의·세션 종료·스피커 대기 중 이탈).
- 미리 만든 음성 파일 위치: `audio/ments/CAUTION.mp3`, `audio/ments/WARNING.mp3`, `audio/ments/NOTICE_PROHIBITED_ITEM.mp3`, `audio/ments/BRIDGE_COMMON.mp3`, 대체 해설 `audio/fallback/A001/01.mp3`. `audio_file`에는 `audio/` 아래 상대 경로를 보낸다.

### 4.4 기록 저장

**침범 기록 열기** `POST /api/records/intrusions`
```json
{"event_id":"evt-20261120-140321123-0001","zone_id":"Z01","artifact_id":"A001",
 "level":"CAUTION","cause":"LINE_1","visitor_ids":[3],
 "started_at":"2026-11-20T14:03:21.123+09:00",
 "session_id":"ses-Z01-20261120-140300000","repeated_caution":false}
```
응답 `{"ok":true,"record_id":128}`

**갱신·닫기** `PATCH /api/records/intrusions/128`
```json
{"event_id":"evt-...-0003","max_level":"WARNING","cause":"CAUTION_TIMEOUT","visitor_ids":[3,5]}
{"event_id":"evt-...-0004","ended_at":"2026-11-20T14:03:31.900+09:00"}
```
`ended_at`이 오면 닫히고 지속 시간을 계산한다. 닫히지 않은 기록은 화면에 "종료 미확인".

**세션 기록** `POST /api/records/sessions` (세션이 끝날 때 한 번)
```json
{"session_id":"ses-Z01-20261120-140300000","zone_id":"Z01","artifact_id":"A001",
 "started_at":"...","ended_at":"...","end_reason":"LEFT_AFTER_COMPLETE",
 "start_count":2,"script_end_count":2,"completed_count":2,
 "script":"지금 보고 계신 유물은 ...","rag_chunk_ids":["A001-03","GC2010-012"],
 "source_urls":["https://www.yna.co.kr/..."],"fallback_used":false}
```

**규칙 위반 기록** `POST /api/records/violations`
```json
{"event_id":"evt-20261120-140400050-0002","zone_id":"Z02","artifact_id":"A002",
 "visitor_id":7,"item_type":"TAKEOUT_CUP","occurred_at":"2026-11-20T14:04:00.050+09:00"}
```
저장 즉시 Flask가 관리자 알림을 띄운다(FR-WEB-05).

### 4.5 상태 통지

`POST /api/agent/state`
```json
{"zone_id":"Z01","session_id":"ses-Z01-20261120-140300000","state":"PAUSED","changed_at":"..."}
```
`POST /api/agent/heartbeat` `{"sent_at":"..."}` 10초마다. 30초 넘게 없으면 "Agent 연결 끊김".

- 현재 해설 문장 표시(FR-WEB-13)는 Flask가 직접 재생하는 문장을 알고 있으므로 Agent가 따로 보내지 않는다.

## 5. 공간 설정 파일 (JSON)

CV 설정 도구가 쓰고, CV·Flask가 읽는다(Flask는 시작 시 1회, 읽기만). 도슨트 구역·안전선 다각형은 **CV가 계산해서 저장**하고 Flask는 그리기만 한다 **[11/3 결정]** (계산이 한 곳에만 있어야 값이 어긋나지 않음).

```json
{
  "version": 1,
  "created_at": "2026-11-10T15:00:00.000+09:00",
  "camera": {"source": "webcam:0", "resolution": [1280, 720]},
  "calibration": {
    "image_points_px": [[212,640],[1050,655],[880,300],[390,295]],
    "floor_points_cm": [[0,0],[400,0],[400,300],[0,300]],
    "homography": [[0.0,0.0,0.0],[0.0,0.0,0.0],[0.0,0.0,1.0]]
  },
  "monitored_area_cm": [[0,0],[400,0],[400,300],[0,300]],
  "speakers": [{"speaker_id": "SPK1", "device": "default"}],
  "zones": [
    {
      "zone_id": "Z01", "artifact_id": "A001", "kind": "SHOWCASE", "speaker_id": "SPK1",
      "roi_cm": [[90,150],[130,150],[130,180],[90,180]],
      "distances_cm": {"docent": 100, "line1": 40, "line2": 20},
      "docent_zone_cm": [[...]], "line1_cm": [[...]], "line2_cm": [[...]],
      "touch_boundary_px": [[500,380],[600,380],[610,470],[495,470]]
    }
  ]
}
```

- `kind`: `SHOWCASE`(탐지 ROI 제안) `OPEN`(오픈 유물, 직접 그림) `WALL`(벽 매몰 진열대).
- 거리 값은 시연 축소값(추천 100·40·20cm, 11/10 측정 후 확정). 운영값 150·60·30cm는 기본값으로 설정 도구에 둔다.
- 도슨트 구역끼리 겹치면 설정 도구가 저장을 막고 알린다(1차 겹침 금지).
- 파일 위치 **[11/3 결정]**: 저장소 `config/space.json`. 시간 기준값·허용 도메인·포트는 `config/settings.yaml`로 분리(NFR-13).

## 6. 결정 체크리스트 (11/3 결정)

- [x] 1. CV → Flask 전송 방식: **Socket.IO** (HTTP POST도 가능했으나 Flask-SocketIO 재사용)
- [x] 2. 재연결 주체: **CV가 5초 간격 재연결**, FR-WEB-16·결정사항 문구 정정
- [x] 3. 이벤트 DTO에 **`seq` 추가**
- [x] 4. Flask → Agent 재생 상태: **상황 조회 0.5초 폴링**
- [x] 5. 공간 설정 파일에 **CV가 계산한 다각형 저장**, Flask는 그리기만
- [x] 6. 좌표 메시지 **`item_type` 포함**
- [x] 7. 포트 **Agent 8765·Flask 5000**, 설정 파일 위치 **`config/`** (`space.json`, `settings.yaml`)
- [x] 8. **세 모듈을 시연 노트북 한 대에서 실행**, 시간 동기화 불필요
- [x] 9. 영문 열거값 이름: 1장 표대로
