# agent/retrieval — 지식 검색 (하이브리드 검색 + Re-ranking)

`agent/knowledge/data/chunks.jsonl`(도록 청크)로 인덱스를 만들고, 관람 판정 이벤트의 `artifact_id`로 근거 청크를 찾는다. MCP 지식 검색 도구(FR-AG-15)가 이 검색기를 감싸서 쓴다.

| 요구사항 | 내용 | 파일 |
|---|---|---|
| FR-AG-02 하이브리드 검색 | artifact_id로 먼저 거르고 BM25 + ChromaDB 벡터 검색, RRF로 합침 | `retriever.py` |
| FR-AG-03 재순위화 | 합친 후보 상위 10개를 CrossEncoder로 다시 점수 매겨 상위 3개 | `retriever.py` |
| 첫 문장 준비 5초 | 유물별 해설 질의의 검색 결과를 Agent 시작 때 미리 계산(근거 캐시) | `evidence_cache.py` |
| NFR-17 검색 정확도 | 평가 질의 20건, 상위 3개 정답 90% 이상·혼입 0건 | `evaluate.py` |
| NFR-13 설정 분리 | 모델·후보 수·사전·동의어를 코드 수정 없이 변경 | `config.yaml` |

## 실행 (Windows PowerShell, Python 3.10 이상)

```powershell
cd agent\retrieval
pip install -r requirements.txt
copy .env.example .env          # OPENAI_API_KEY 입력 (저장소에 올라가지 않음, NFR-11)

python build_index.py           # 인덱스 빌드 → chroma_db\ (청크가 바뀔 때만 다시 실행)
python evaluate.py --no-rerank  # 하이브리드 검색만 평가
python evaluate.py              # Re-ranking 포함 평가 (처음 실행 때 bge-reranker-v2-m3 약 2.3GB 다운로드)
python retriever.py A001 "금령총 금관의 특징"   # 검색 한 건 확인
python evidence_cache.py --show A001            # 근거 캐시 만들기(바뀐 게 없으면 기존 파일 사용)·확인
```

평가 결과는 `eval_results\<시각>_<임베딩>_<rerank|norerank>.json`에 남아 설정끼리 비교할 수 있다.

## 동작

1. **거르기**: 청크의 `artifact_ids`에 해당 유물이 있는 청크만 후보로 둔다(ChromaDB 메타데이터 `art_A001: true`).
   - **검색용 머리말**: BM25·벡터·Re-ranking에는 청크 앞에 `[유물명]`(`agent/knowledge/targets.json` 표기)을 붙인 텍스트를 쓴다. '함께 발견된 유물로는 …'처럼 유물명이 앞 청크에만 있는 청크도 어느 유물 이야기인지 드러나게 하기 위함이다. 결과의 `text`와 `chunks.jsonl` 원문은 그대로다. `chunk_header.enabled`로 켜고 끄며, 켜면 컬렉션 이름 끝에 `_name`이 붙어 머리말 없는 인덱스와 따로 저장된다.
2. **BM25**: kiwi 형태소 분석으로 내용어만 남겨 점수를 매긴다. `user_words`(잘못 잘리는 유물 용어)와 `synonyms`(곡옥↔곱은옥, 나오↔출토·발견 등 질의·도록 표현 차이)는 `config.yaml`에서 관리한다. 동의어는 품사와 관계없이 질의의 모든 형태소에서 찾는다(kiwi가 '언제'를 부사, '만드는'의 '만들'을 보조용언으로 잘라 내용어에서 빠지는 경우 대비). 청크가 200개 수준이라 검색기를 켤 때 메모리에서 바로 만든다.
3. **벡터**: OpenAI `text-embedding-3-small`. 청크 벡터는 빌드 때 한 번 만들어 저장하고, 관람 중에는 질의 1개만 임베딩한다(같은 질의는 캐시).
4. **RRF**: 두 순위를 `1/(60+순위)`로 더해 합친다(BM25 점수와 코사인 유사도는 크기가 달라 그대로 더할 수 없음).
5. **배경 제한**: `kind: background`(시대 배경) 청크는 결과와 재순위화 후보에 `background_max`(1)개까지만 넣는다. A001은 강의 자료 배경 청크가 52개라 제한이 없으면 유물 고유 설명이 상위에서 밀린다.
6. **Re-ranking**: `BAAI/bge-reranker-v2-m3`를 CPU에서 실행(후보 10개, `max_length` 320). 시연 노트북(RAM 16GB, GPU 없음)에서 CV와 코어를 나눠 쓰도록 `torch_threads: 2`로 제한. 끄려면 `reranker.enabled: false`.

결과 항목: `chunk_id`, `artifact_ids`, `kind`, `text`, `caution`, `source`, `scores`(BM25 순위·벡터 순위·RRF·재순위 점수). 해설 생성 시 `kind: background`는 시대 배경으로만 쓰고, `caution`은 근거와 함께 LLM에 넘겨 e뮤지엄 기준값을 따르게 한다. 세션 기록의 도록 근거에는 `chunk_id`를 그대로 남긴다.

## 근거 캐시 (`evidence_cache.py`)

Re-ranking은 CPU에서 질의당 약 9~11초라 관람 판정 → 첫 문장 준비 5초 안에 할 수 없다. 관람 판정 때의 검색 질의는 관람객이 아니라 Agent가 정하므로(유물마다 같은 해설 질의), Agent 시작 때 유물별 결과를 미리 계산해 둔다. 청크와 질의가 같으면 결과도 같아서 관람 판정 때 검색한 것과 같다. **저장하는 것은 근거 청크뿐이고, 도슨트 스크립트는 관람 판정 시점에 이 근거와 최신 소식으로 LLM이 실시간 생성한다.**

- 질의: `config.yaml`의 `evidence_cache.topics`(intro·making·features·history·behind, 해설 구성 ① 도입 ② 도록 핵심 설명에 맞춤) × `artifacts`(유물 이름). 주제마다 상위 `per_topic`(8)개 저장(Re-ranking 후보가 10개라 늘려도 빌드 시간은 같음)
- `evidence(artifact_id)`: 주제별 1위, 2위 … 순으로 번갈아 합쳐 중복을 뺀 `evidence_limit`(8)개. 합친 결과에도 배경 청크는 `background_max`(1)개까지(질의 하나 기준 제한이라 주제마다 1개씩 쌓이므로). 자리가 남으면 배경이 아니라 검색에 안 걸린 그 유물의 고유 청크로 채운다(A001은 고유 청크 7개가 모두 들어감, 다른 금관의 제작 연대를 다룬 GC2010-035 같은 배경이 빈자리를 차지하지 않게). 해설마다 다른 근거를 섞어 쓰려면 `get()`의 주제별 결과에서 고른다
- 무효화: 청크 파일·검색 설정(임베딩·BM25·하이브리드·Re-ranker 모델·후보 수·max_length·배경 제한·검색용 머리말과 유물명 파일)·캐시 질의의 해시를 함께 저장. 하나라도 바뀌면 다음 시작 때 다시 만든다(유물 4점 × 주제 5개 약 3분, 이때만 Re-ranker 약 2.3GB를 올렸다가 내림). 시연 전에 `python evidence_cache.py`로 미리 만들어 두면 시작은 캐시 읽기만 한다(약 6초, 대부분 실시간 검색기 준비)
- 캐시에 없는 질의·유물: `cache.search()`가 Re-ranking 없이 하이브리드로 바로 검색(약 0.2초, 대부분 질의 임베딩 API)
- 파일: `cache/evidence_cache.json`(.gitignore 대상)

### Re-ranker 비교 (2026-11-04, 평가 질의 20건, max_length 320·background_max 1)

| 설정 | 정답 포함 | 혼입 | 질의당 평균 |
|---|---|---|---|
| 하이브리드만 | 17/20 | 0 | 0.2초 |
| bge-reranker-v2-m3, 후보 10개 (채택) | 18/20 | 0 | 8.8초 |

머리말 적용 뒤 결과는 아래 "검색용 머리말 비교" 참고(20/20).
| bge-reranker-v2-m3, 후보 5개 | 17/20 | 0 | 4.4초 |
| jina-reranker-v2-base-multilingual, 후보 10개 | 17/20 | 0 | 3.0초 |

- 후보 수가 정확도 상한: 정답이 하이브리드 5·7·9위인 질의가 있어 후보 5개면 최대 18/20, 10개면 20/20
- jina는 transformers 5.x와 원격 코드가 맞지 않고(빠진 함수 보완 필요) 기본 bf16 로드가 CPU에서 매우 느려 float32 강제가 필요. `reranker.trust_remote_code: true`로 로드 가능

### 검색용 머리말 비교 (2026-11-05, bge-reranker-v2-m3 후보 10개)

| 머리말 | 하이브리드만 | Re-ranking 포함 | 혼입 | Re-ranking 질의당 평균 |
|---|---|---|---|---|
| 없음 | 17/20 | 18/20 (Q04·Q13 실패) | 0 | 9.0초 |
| `[유물명]` + 출처 제목·섹션 | 17/20 (Q07·Q08·Q11 실패) | 측정 안 함 | 0 | - |
| `[유물명]` (채택) | 18/20 (Q03·Q07 실패) | **20/20** (2회 측정) | 0 | 9.4~11.4초 |

- 머리말 없음의 실패 원인: Q04 정답 `A001-05`("함께 발견된 유물로는 …")와 Q13 정답 `CUR001-009`("다만 차이가 있다면 …")에 유물명·주제가 없음
- 출처 제목까지 넣으면 큐레이터 자료처럼 제목이 긴 자료는 모든 청크가 같은 제목을 달아 임베딩이 서로 비슷해지고, 제목 단어('만든 불상' 등)가 질의와 겹쳐 정답이 밀림. A003은 큐레이터 제목이 유물명과 같아 유물명이 두 번 들어가 e뮤지엄 청크가 밀림
- Re-ranking 질의당 시간은 두 번 측정에서 9.4초·11.4초로 머리말 없을 때(9.0초)와 측정 편차 수준. 관람 중에는 근거 캐시를 쓰므로 영향 없음
- 하이브리드만(캐시에 없는 질의에 쓰는 검색)도 17/20 → 18/20으로 목표 달성
- 거르지 않은 검색(혼동 테스트)에서는 Q04에 서봉총 함께 출토 유물(`D002-05`), Q15에 이름이 같은 다른 대접(`D006-01`)이 상위 3개에 들어옴. 실제 검색은 `artifact_id`로 거르므로 혼입 0건

## 설정 바꾸기

- 임베딩 모델을 바꾸면 컬렉션 이름이 달라져(`chunks_openai_text_embedding_3_small` 등) 이전 인덱스와 섞이지 않는다. 바꾼 뒤 `build_index.py`를 다시 실행한다.
- `embedding.backend: hash`는 API 키·네트워크 없이 흐름만 확인하는 테스트용이다(정확도 의미 없음, NFR-14 단독 테스트용).
- 평가에서 틀린 질의가 있으면 `top3`와 `scores`를 보고 `user_words`·`synonyms`·후보 수를 조정한 뒤 다시 평가한다.
