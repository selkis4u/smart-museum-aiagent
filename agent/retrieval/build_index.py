"""도록 청크(agent/knowledge/data/chunks.jsonl)로 ChromaDB 벡터 인덱스를 만든다.

사용법
  python build_index.py              # config.yaml 설정으로 빌드(같은 모델 컬렉션은 지우고 다시 만듦)
  python build_index.py --check      # 저장된 인덱스의 청크 수·유물별 개수만 확인

- 청크가 바뀌었을 때만 다시 돌린다. 관람 중에는 실행하지 않는다(검색기는 저장된 인덱스를 읽기만 함).
- BM25는 청크가 209개 수준이라 검색기를 켤 때 메모리에서 바로 만든다(따로 저장하지 않음).
"""

import sys
import time
from collections import Counter

import chromadb

from common import (artifact_key, artifact_names, collection_name, header_on, load_config, load_jsonl,
                    make_embedder, search_text)


def metadata(c: dict) -> dict:
    meta = {
        "chunk_id": c["chunk_id"],
        "kind": c["kind"],
        "role": c["role"],
        "artifact_ids": "|".join(c["artifact_ids"]),  # 표시용. 거르기는 art_* 키로 한다
        "has_caution": bool(c.get("caution")),
    }
    for a in c["artifact_ids"]:
        meta[artifact_key(a)] = True
    return meta


def build(cfg: dict):
    chunks = load_jsonl(cfg["chunks"])
    name = collection_name(cfg)
    print(f"청크 {len(chunks)}개 → 컬렉션 {name} ({cfg['chroma_dir']})")

    names = artifact_names(cfg) if header_on(cfg) else None
    print(f"검색용 머리말: {'켬' if names else '끔'}")
    t0 = time.time()
    vectors = make_embedder(cfg).embed([search_text(c, names) for c in chunks])
    print(f"임베딩 완료: {time.time() - t0:.1f}초, 차원 {len(vectors[0])}")

    client = chromadb.PersistentClient(path=str(cfg["chroma_dir"]))
    if name in [c.name for c in client.list_collections()]:
        client.delete_collection(name)
    col = client.create_collection(name, metadata={"hnsw:space": "cosine"})
    col.add(
        ids=[c["chunk_id"] for c in chunks],
        embeddings=vectors,
        documents=[c["text"] for c in chunks],
        metadatas=[metadata(c) for c in chunks],
    )
    check(cfg)


def check(cfg: dict):
    client = chromadb.PersistentClient(path=str(cfg["chroma_dir"]))
    col = client.get_collection(collection_name(cfg))
    metas = col.get(include=["metadatas"])["metadatas"]
    per = Counter(a for m in metas for a in m["artifact_ids"].split("|") if a)
    print(f"저장된 청크 {col.count()}개")
    print("유물별:", " · ".join(f"{a} {n}" for a, n in sorted(per.items())))


if __name__ == "__main__":
    cfg = load_config()
    check(cfg) if "--check" in sys.argv else build(cfg)
