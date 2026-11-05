"""근거 캐시: 유물별 도록 근거 청크를 Agent 시작 때 미리 검색해 둔다.

관람 판정 → 첫 문장 준비 5초(NFR) 안에 Re-ranking(CPU에서 질의당 약 9초)을 할 수 없어서,
유물마다 정해진 해설 질의(config.yaml evidence_cache.topics)의 검색 결과를 미리 계산한다.
도록 청크와 질의가 같으면 검색 결과도 같으므로 관람 판정 때 검색한 것과 결과가 같다.
도슨트 스크립트는 그대로 관람 판정 시점에 이 근거와 최신 소식으로 LLM이 실시간 생성한다(원고를 미리 만드는 것이 아님).

    from evidence_cache import EvidenceCache
    cache = EvidenceCache.load_or_build()        # Agent 시작 때 1회
    hits = cache.evidence("A001")                # 해설 생성에 넘길 근거(주제별 결과를 번갈아 합침)
    by_topic = cache.get("A001")                 # {"intro": [...], "making": [...], ...}
    cache.search("A001", "다른 질의")             # 캐시에 없는 질의는 하이브리드 검색(Re-ranking 없음, 0.2초 안팎)

사용법
  python evidence_cache.py            # 캐시 만들기(바뀐 것이 없으면 기존 파일 그대로 사용)
  python evidence_cache.py --rebuild  # 강제로 다시 만들기
  python evidence_cache.py --show A001

- 캐시 파일에는 청크 파일·검색 설정·질의의 해시를 함께 저장한다. 하나라도 바뀌면 다음 시작 때 다시 만든다.
- 만들 때만 Re-ranker(약 2.3GB)를 메모리에 올리고 끝나면 내린다. 캐시 파일이 맞으면 Re-ranker를 올리지 않는다.
"""

import gc
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from common import HERE, header_on, load_config
from retriever import Retriever

# 캐시 결과를 바꾸는 설정만 해시에 넣는다(경로·스레드 수 등은 제외)
_HASH_KEYS = ("embedding", "bm25", "hybrid", "background_max")
_RERANK_HASH_KEYS = ("enabled", "model", "candidates", "max_length")


def fingerprint(cfg: dict) -> str:
    ec = cfg["evidence_cache"]
    payload = {
        "chunks": hashlib.sha256(cfg["chunks"].read_bytes()).hexdigest(),
        "cfg": {k: cfg.get(k) for k in _HASH_KEYS},
        "reranker": {k: cfg["reranker"].get(k) for k in _RERANK_HASH_KEYS},
        # 머리말: 켬/끔과 유물명 출처(targets.json) 내용. 경로는 PC마다 달라 넣지 않는다
        "chunk_header": {"enabled": header_on(cfg),
                         "targets": hashlib.sha256(Path(cfg["chunk_header"]["targets"]).read_bytes()).hexdigest()
                         if header_on(cfg) else None},
        "cache": {k: ec[k] for k in ("artifacts", "topics", "per_topic")},
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


class EvidenceCache:
    def __init__(self, cfg: dict, data: dict):
        self.cfg = cfg
        self.data = data                 # {"fingerprint", "built_at", "artifacts": {aid: {topic: [hit]}}}
        # 캐시에 없는 질의·유물용 하이브리드 검색기. 첫 호출 때 만들면 kiwi·BM25·ChromaDB 준비로 수 초가 걸려 미리 만든다
        self._live = Retriever(cfg, rerank=False)

    # ------------------------------------------------------------ 만들기·읽기

    @classmethod
    def load_or_build(cls, cfg: dict | None = None, rebuild: bool = False) -> "EvidenceCache":
        cfg = cfg or load_config()
        path = cfg["evidence_cache"]["path"]
        fp = fingerprint(cfg)
        if not rebuild and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("fingerprint") == fp:
                return cls(cfg, data)
            print(f"[근거 캐시] 청크·설정이 바뀌어 다시 만듭니다 ({data.get('fingerprint')} → {fp})")
        return cls(cfg, cls._build(cfg, fp))

    @staticmethod
    def _build(cfg: dict, fp: str) -> dict:
        ec = cfg["evidence_cache"]
        r = Retriever(cfg)               # config의 reranker.enabled를 따름
        t0 = time.perf_counter()
        arts = {}
        for aid, name in ec["artifacts"].items():
            arts[aid] = {topic: r.search(aid, tmpl.format(name=name), ec["per_topic"])
                         for topic, tmpl in ec["topics"].items()}
            print(f"[근거 캐시] {aid} {name}: 주제 {len(ec['topics'])}개 완료 ({time.perf_counter() - t0:.0f}초)")
        del r
        gc.collect()                     # Re-ranker 메모리 반환(CV와 같은 노트북에서 실행)

        data = {"fingerprint": fp, "built_at": datetime.now().isoformat(timespec="seconds"), "artifacts": arts}
        path = ec["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)                # 쓰는 도중 끊겨도 기존 캐시가 깨지지 않게
        print(f"[근거 캐시] 저장: {path}")
        return data

    # ------------------------------------------------------------ 조회

    def has(self, artifact_id: str) -> bool:
        return artifact_id in self.data["artifacts"]

    def get(self, artifact_id: str) -> dict[str, list[dict]]:
        """주제별 근거. 캐시에 없는 유물(새로 등록 등)은 하이브리드 검색으로 바로 만든다."""
        if self.has(artifact_id):
            return self.data["artifacts"][artifact_id]
        ec = self.cfg["evidence_cache"]
        name = ec["artifacts"].get(artifact_id, artifact_id)
        print(f"[근거 캐시] {artifact_id} 캐시 없음 → 하이브리드 검색")
        return {topic: self.search(artifact_id, tmpl.format(name=name), ec["per_topic"])
                for topic, tmpl in ec["topics"].items()}

    def evidence(self, artifact_id: str, limit: int | None = None) -> list[dict]:
        """해설 생성에 넘길 근거: 주제별 1위, 2위 … 순으로 번갈아 합치고 중복 청크는 뺀다.

        background_max는 질의 하나 기준이라 주제 5개를 합치면 배경 청크가 주제마다 1개씩 쌓인다.
        합친 근거에도 같은 제한을 다시 건다. 자리가 남으면 배경이 아니라 아직 안 들어간 그 유물의
        고유 청크(meta·desc·note, 청크 순서대로)로 채운다. A001처럼 고유 청크가 적은 유물은 검색 순위와
        관계없이 고유 청크가 모두 들어가고, 다른 금관 이야기인 배경 청크가 빈자리를 차지하지 않는다.
        """
        limit = limit or self.cfg["evidence_cache"]["evidence_limit"]
        cap = self.cfg.get("background_max")
        topics = list(self.get(artifact_id).values())
        merged, seen = [], set()
        for rank in range(max((len(t) for t in topics), default=0)):
            for hits in topics:
                if rank < len(hits) and hits[rank]["chunk_id"] not in seen:
                    seen.add(hits[rank]["chunk_id"])
                    merged.append(hits[rank] | {"topic_rank": rank + 1})
        out, bg = [], 0
        for h in merged:
            if cap is not None and h["kind"] == "background":
                if bg >= cap:
                    continue
                bg += 1
            out.append(h)
            if len(out) == limit:
                return out
        for c in self._live.chunks:      # 남은 자리: 검색에 안 걸린 고유 청크
            if len(out) == limit:
                break
            if artifact_id in c["artifact_ids"] and c["kind"] != "background" and c["chunk_id"] not in seen:
                out.append({"chunk_id": c["chunk_id"], "artifact_ids": c["artifact_ids"], "kind": c["kind"],
                            "text": c["text"], "caution": c.get("caution", []), "source": c.get("source", {}),
                            "scores": None, "topic_rank": None})
        return out

    def search(self, artifact_id: str, query: str, top_k: int | None = None) -> list[dict]:
        """캐시에 없는 질의용 실시간 검색. 5초 예산을 지키도록 Re-ranking 없이 하이브리드만 쓴다."""
        return self._live.search(artifact_id, query, top_k)


if __name__ == "__main__":
    cache = EvidenceCache.load_or_build(rebuild="--rebuild" in sys.argv)
    print(f"근거 캐시 {cache.data['fingerprint']} (만든 시각 {cache.data['built_at']})")
    if "--show" in sys.argv:
        aid = sys.argv[sys.argv.index("--show") + 1]
        for topic, hits in cache.get(aid).items():
            print(f"[{topic}]", ", ".join(f"{h['chunk_id']}({h['kind']})" for h in hits))
        print("evidence:", [h["chunk_id"] for h in cache.evidence(aid)])
