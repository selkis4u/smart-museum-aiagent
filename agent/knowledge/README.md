# agent/knowledge — 지식 검색(RAG) 자료 준비

시연 유물의 공식 해설과 공개 자료를 모아 청크로 만든다. 결과 `data/chunks.jsonl`이 임베딩·ChromaDB·BM25 인덱스의 입력이다.

## 시연 유물

| artifact_id | 유물 | 소장품번호 |
|---|---|---|
| A001 | 금령총 금관 (보물) | 본관9663 |
| A002 | 지장암 목조비로자나불좌상 (보물, 1622년) + 복장물 3건(조성기·다라니·후령통) | 구10416, 구10417·10422·10423 |
| A003 | 백자 상감 연꽃 넝쿨무늬 대접 (국보) — 쇼케이스 교체용 | 동원887 |
| A004 | 「천흥사」가 새겨진 천흥사 동종 (국보, 1010년) — 오픈 유물 교체용 | 덕수2445 |
| D001~D005 | 혼동 테스트용 (금관총·서봉총 금관, 석조비로자나불좌상 3점) | targets.json 참고 |
| D009~D011 | A004 혼동 테스트용 (「청녕 사년」명 동종, 「천안광덕사」가 새겨진 동종, 성거산 천흥사 종명) | targets.json 참고 |
| D006~D008 | A003 혼동 테스트용 (같은 이름의 백자 대접 동원95, 분청사기·청자 상감 연꽃 넝쿨무늬 대접) | targets.json 참고 |

## 실행

```powershell
pip install -r requirements.txt
copy .env.example .env      # EMUSEUM_API_KEY에 공공데이터포털 인증키(Decoding) 입력

python emuseum_collect.py search 금관                 # 유물 찾기
python emuseum_collect.py build                       # targets.json 유물을 API로 받아 청크 생성
python emuseum_collect.py build --offline             # 저장된 data/raw로 청크만 다시 생성
python pdf_collect.py sources/gold_crown_2010.json    # PDF 청크 생성(docs/ 에 PDF 필요)
python pdf_collect.py sources/bulgoksa_2011.json
python text_collect.py sources/curator_a003.json  # 웹 글(큐레이터 추천) 청크 생성(docs/ 에 원문 필요)
python text_collect.py sources/curator_a004.json
python text_collect.py sources/curator_a002.json
```

각 명령은 끝날 때 `data/chunks_*.jsonl`을 모아 `data/chunks.jsonl`을 다시 만든다.

## 폴더

- `targets.json` 수집 대상. id 대신 `"relic": "구10416", "search": "지장암"`을 적으면 build가 id를 찾아 채운다
- `sources/` PDF·웹 글별 설정: 제목 규칙, 글자 크기, 장·절(또는 문단)과 artifact_ids 연결
- `docs/` 원본 PDF·웹 글 텍스트 — 저작권 때문에 Git에 올리지 않는다(.gitignore). 팀 공유 드라이브에서 받아 넣을 것
  - `curator_A003_1569299.txt`: 국립중앙박물관 큐레이터 추천 「백자 상감 연꽃 넝쿨무늬 대접」(권소현), 공공누리 제3유형(출처표시+변경금지). 원문을 고치지 않고 청크로만 쓰고, 해설에는 문장을 그대로 옮기지 않는다
  - `curator_A004_16862.txt`: 국립중앙박물관 큐레이터 추천 「천흥사 종」(채해정), 공공누리 제3유형(출처표시+변경금지). 높이 187cm는 e뮤지엄 174.2cm와 달라 e뮤지엄 값을 쓴다
  - `curator_A002_2351278.txt`: 국립중앙박물관 큐레이터 추천 「목조비로자나여래좌상 - 왕비의 부름으로 집결한 승려 장인들이 함께 만든 불상」(유수란), 공공누리 제3유형(출처표시+변경금지). 왕비 이름 표기가 e뮤지엄('장열')과 다름('장렬'). 해설은 e뮤지엄 표기를 따른다
- `data/` 청크와 API 원본 응답(Git에 올림)
- `fallback/` 대체 해설 원고(문장별 음성 파일로 만들 원고). A001·A002, A003·A004
- `eval/` 검색 평가 질의(NFR-17) 20건과 설명

## 청크 형식

```json
{"chunk_id": "A002R1-03", "artifact_ids": ["A002"], "role": "target", "kind": "desc",
 "text": "…", "source": {"org": "국립중앙박물관", "license": "공공누리 제1유형(출처표시)"}}
```

- `kind`: `meta` 기본 정보 · `desc` 설명 · `note` 각주 비하인드 · `background` 시대 배경(그 유물의 사실로 말하지 않음)
- 검색은 관람 판정 이벤트의 artifact_id로 `artifact_ids`를 먼저 거른 뒤 BM25·벡터 검색
- 규칙의 근거는 `docs/requirements/decisions.md` 참고
