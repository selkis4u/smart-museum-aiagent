# agent/knowledge — 지식 검색(RAG) 자료 준비

시연 유물의 공식 해설과 공개 자료를 모아 청크로 만든다. 결과 `data/chunks.jsonl`이 임베딩·ChromaDB·BM25 인덱스의 입력이다.

## 시연 유물

| artifact_id | 유물 | 소장품번호 |
|---|---|---|
| A001 | 금령총 금관 (보물) | 본관9663 |
| A002 | 지장암 목조비로자나불좌상 (보물, 1622년) + 복장물 3건(조성기·다라니·후령통) | 구10416, 구10417·10422·10423 |
| D001~D005 | 혼동 테스트용 (금관총·서봉총 금관, 석조비로자나불좌상 3점) | targets.json 참고 |

## 실행

```powershell
pip install -r requirements.txt
copy .env.example .env      # EMUSEUM_API_KEY에 공공데이터포털 인증키(Decoding) 입력

python emuseum_collect.py search 금관                 # 유물 찾기
python emuseum_collect.py build                       # targets.json 유물을 API로 받아 청크 생성
python emuseum_collect.py build --offline             # 저장된 data/raw로 청크만 다시 생성
python pdf_collect.py sources/gold_crown_2010.json    # PDF 청크 생성(docs/ 에 PDF 필요)
python pdf_collect.py sources/bulgoksa_2011.json
```

각 명령은 끝날 때 `data/chunks_*.jsonl`을 모아 `data/chunks.jsonl`을 다시 만든다.

## 폴더

- `targets.json` 수집 대상. id 대신 `"relic": "구10416", "search": "지장암"`을 적으면 build가 id를 찾아 채운다
- `sources/` PDF별 설정: 제목 규칙, 글자 크기, 장·절과 artifact_ids 연결
- `docs/` 원본 PDF — 저작권 때문에 Git에 올리지 않는다(.gitignore). 팀 공유 드라이브에서 받아 넣을 것
- `data/` 청크와 API 원본 응답(Git에 올림)
- `fallback/` 대체 해설 원고(문장별 음성 파일로 만들 원고)

## 청크 형식

```json
{"chunk_id": "A002R1-03", "artifact_ids": ["A002"], "role": "target", "kind": "desc",
 "text": "…", "source": {"org": "국립중앙박물관", "license": "공공누리 제1유형(출처표시)"}}
```

- `kind`: `meta` 기본 정보 · `desc` 설명 · `note` 각주 비하인드 · `background` 시대 배경(그 유물의 사실로 말하지 않음)
- 검색은 관람 판정 이벤트의 artifact_id로 `artifact_ids`를 먼저 거른 뒤 BM25·벡터 검색
- 규칙의 근거는 `docs/requirements/decisions.md` 참고
