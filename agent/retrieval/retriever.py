"""하이브리드 검색(FR-AG-02) + 재순위화(FR-AG-03).

흐름: artifact_id로 청크 거르기 → BM25·벡터 검색 → RRF로 합치기 → (켜져 있으면) CrossEncoder 재순위화 → 상위 top_k

    from retriever import Retriever
    r = Retriever()
    hits = r.search("A001", "금령총 금관의 특징")
    for h in hits: print(h["chunk_id"], h["kind"], h["text"][:40])

- 결과의 kind가 background면 시대 배경으로만, caution이 있으면 함께 LLM에 넘겨 기준값(e뮤지엄)을 따르게 한다.
- artifact_id=None이면 거르지 않고 전체에서 검색한다(평가의 혼동 테스트용).
"""

import time
from functools import lru_cache

import chromadb
from rank_bm25 import BM25Okapi

from common import artifact_key, collection_name, load_config, load_jsonl, make_embedder, query_tokens, tokenize


class Retriever:
    def __init__(self, cfg: dict | None = None, rerank: bool | None = None):
        self.cfg = cfg or load_config()
        self.chunks = load_jsonl(self.cfg["chunks"])
        self.by_id = {c["chunk_id"]: c for c in self.chunks}
        self.ids = [c["chunk_id"] for c in self.chunks]

        self.bm25 = BM25Okapi([tokenize(c["text"], self.cfg["bm25"]) for c in self.chunks])

        client = chromadb.PersistentClient(path=str(self.cfg["chroma_dir"]))
        name = collection_name(self.cfg)
        try:
            self.col = client.get_collection(name)
        except Exception:
            raise SystemExit(f"인덱스 {name}이 없습니다. 먼저 python build_index.py 를 실행하세요.")
        if self.col.count() != len(self.chunks):
            print(f"[경고] 인덱스 청크 {self.col.count()}개 ≠ chunks.jsonl {len(self.chunks)}개 → build_index.py 다시 실행 권장")

        self.embedder = make_embedder(self.cfg)
        rr = self.cfg["reranker"]
        self.rerank_on = rr["enabled"] if rerank is None else rerank
        self.reranker = self._load_reranker(rr) if self.rerank_on else None
        self.last_timing: dict = {}

    @staticmethod
    def _load_reranker(rr: dict):
        try:
            import torch
            from sentence_transformers import CrossEncoder
        except ImportError:
            raise SystemExit("Re-ranker에 sentence-transformers가 필요합니다: pip install sentence-transformers "
                             "(또는 config.yaml에서 reranker.enabled: false)")
        torch.set_num_threads(rr.get("torch_threads", 2))
        # trust_remote_code: jina-reranker-v2처럼 모델 저장소의 코드를 쓰는 모델만 config에서 켠다
        return CrossEncoder(rr["model"], max_length=rr.get("max_length", 512), device="cpu",
                            trust_remote_code=rr.get("trust_remote_code", False))

    @lru_cache(maxsize=256)
    def _query_vector(self, query: str) -> tuple:
        return tuple(self.embedder.embed([query])[0])

    def _candidates(self, artifact_id: str | None) -> set[str]:
        if artifact_id is None:
            return set(self.ids)
        return {c["chunk_id"] for c in self.chunks if artifact_id in c["artifact_ids"]}

    def _cap_background(self, ranked: list[str], n: int) -> list[str]:
        """순위대로 n개를 고르되 kind=background(시대 배경)는 background_max개까지만.

        A001처럼 강의 자료 배경 청크가 많은 유물에서 배경이 상위를 차지해 유물 고유 설명이 밀리지 않도록.
        재순위화 후보에도 같은 제한을 둬서 버려질 배경 청크에 Re-ranking 시간을 쓰지 않는다.
        배경 아닌 청크가 모자라면 남은 자리는 배경으로 채운다.
        """
        cap = self.cfg.get("background_max")
        if cap is None:
            return ranked[:n]
        picked, skipped, bg = [], [], 0
        for cid in ranked:
            if self.by_id[cid]["kind"] == "background":
                if bg >= cap:
                    skipped.append(cid)
                    continue
                bg += 1
            picked.append(cid)
            if len(picked) == n:
                return picked
        return picked + skipped[: n - len(picked)]

    def search(self, artifact_id: str | None, query: str, top_k: int | None = None) -> list[dict]:
        h = self.cfg["hybrid"]
        top_k = top_k or self.cfg["top_k"]
        cand = self._candidates(artifact_id)
        if not cand:
            return []
        t = {}

        # 1) BM25: IDF는 전체 청크 기준, 점수는 후보만
        t0 = time.perf_counter()
        scores = self.bm25.get_scores(query_tokens(query, self.cfg["bm25"]))
        bm25_rank = sorted((i for i in range(len(self.ids)) if self.ids[i] in cand and scores[i] > 0),
                           key=lambda i: -scores[i])[: h["bm25_top"]]
        bm25_ids = [self.ids[i] for i in bm25_rank]
        t["bm25"] = time.perf_counter() - t0

        # 2) 벡터: ChromaDB에서 같은 artifact_id로 거른 뒤 검색
        t0 = time.perf_counter()
        qv = list(self._query_vector(query))
        t["embed"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        res = self.col.query(
            query_embeddings=[qv],
            n_results=min(h["vector_top"], len(cand)),
            where={artifact_key(artifact_id): True} if artifact_id else None,
        )
        vec_ids = res["ids"][0]
        t["vector"] = time.perf_counter() - t0

        # 3) RRF: 두 순위를 1/(k+순위)로 더한다(점수 크기가 달라도 합칠 수 있음)
        k = h["rrf_k"]
        rrf: dict[str, float] = {}
        for ranked in (bm25_ids, vec_ids):
            for r, cid in enumerate(ranked, 1):
                rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (k + r)
        fused = sorted(rrf, key=lambda c: -rrf[c])

        # 4) 재순위화: 질의·청크 쌍을 CrossEncoder로 다시 점수 매김
        rerank_scores = {}
        t0 = time.perf_counter()
        if self.reranker is not None:
            pool = self._cap_background(fused, self.cfg["reranker"]["candidates"])
            s = self.reranker.predict([(query, self.by_id[c]["text"]) for c in pool])
            rerank_scores = dict(zip(pool, map(float, s)))
            fused = sorted(pool, key=lambda c: -rerank_scores[c])
        t["rerank"] = time.perf_counter() - t0
        self.last_timing = t

        out = []
        for cid in self._cap_background(fused, top_k):
            c = self.by_id[cid]
            out.append({
                "chunk_id": cid,
                "artifact_ids": c["artifact_ids"],
                "kind": c["kind"],
                "text": c["text"],
                "caution": c.get("caution", []),
                "source": c.get("source", {}),
                "scores": {
                    "bm25_rank": bm25_ids.index(cid) + 1 if cid in bm25_ids else None,
                    "vector_rank": vec_ids.index(cid) + 1 if cid in vec_ids else None,
                    "rrf": round(rrf[cid], 5),
                    "rerank": round(rerank_scores[cid], 4) if cid in rerank_scores else None,
                },
            })
        return out


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("사용법: python retriever.py A001 \"금령총 금관의 특징\" [--no-rerank]")
        sys.exit()
    r = Retriever(rerank=False if "--no-rerank" in sys.argv else None)
    for hit in r.search(sys.argv[1], sys.argv[2]):
        print(hit["chunk_id"], hit["kind"], hit["scores"], hit["text"][:60].replace("\n", " "))
        for c in hit["caution"]:
            print("   주의:", c)
    print("시간(초):", {k: round(v, 3) for k, v in r.last_timing.items()})
