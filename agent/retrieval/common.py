"""검색 모듈 공통: 설정·청크 읽기, 임베딩, BM25 토크나이저.

build_index.py · retriever.py · evaluate.py가 함께 쓴다.
"""

import hashlib
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")         # agent/retrieval/.env
load_dotenv(HERE.parent / ".env")  # agent/.env (Agent 공용 키를 둘 경우)


def load_config(path: Path | None = None) -> dict:
    cfg = yaml.safe_load((path or HERE / "config.yaml").read_text(encoding="utf-8"))
    for key in ("chunks", "eval_queries", "chroma_dir"):
        cfg[key] = (HERE / cfg[key]).resolve()
    if cfg.get("chunk_header", {}).get("targets"):
        cfg["chunk_header"]["targets"] = (HERE / cfg["chunk_header"]["targets"]).resolve()
    if "evidence_cache" in cfg:
        cfg["evidence_cache"]["path"] = (HERE / cfg["evidence_cache"]["path"]).resolve()
    return cfg


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def collection_name(cfg: dict) -> str:
    """임베딩 모델마다 컬렉션을 따로 둔다(모델을 바꿔도 이전 인덱스와 섞이지 않게)."""
    emb = cfg["embedding"]
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", f"{emb['backend']}_{emb['model']}").strip("_").lower()
    if header_on(cfg):
        slug += "_name"  # 머리말을 붙여 만든 벡터는 컬렉션을 따로 둔다(켜고 끄며 비교해도 섞이지 않게)
    return f"chunks_{slug}"[:63]


# ---------------------------------------------------------------- 검색용 머리말

def header_on(cfg: dict) -> bool:
    return bool(cfg.get("chunk_header", {}).get("enabled"))


def artifact_names(cfg: dict) -> dict[str, str]:
    """유물 ID → 유물명(targets.json memo의 첫 쉼표 앞). 같은 ID가 여럿이면(복장물 등) 첫 항목이 유물 자체."""
    names: dict[str, str] = {}
    for t in json.loads(Path(cfg["chunk_header"]["targets"]).read_text(encoding="utf-8")):
        names.setdefault(t["artifact_id"], t["memo"].split(",")[0].strip())
    return names


def search_text(chunk: dict, names: dict[str, str] | None) -> str:
    """검색에 쓰는 텍스트 = [유물명] 머리말 + 청크 원문.

    '함께 발견된 유물로는 …'·'다만 차이가 있다면 …'처럼 유물명이 앞 청크에만 있는 청크도
    어느 유물의 이야기인지 검색에서 드러나게 한다. names=None이면 원문 그대로.
    출처 제목·섹션은 넣지 않는다: 큐레이터 자료처럼 제목이 긴 자료는 모든 청크가 같은 제목을 달아
    임베딩이 서로 비슷해지고, 제목의 단어(예: '만든 불상')가 질의와 겹쳐 정답 청크가 밀렸다(11/5 측정).
    """
    if names is None:
        return chunk["text"]
    art = " · ".join(names.get(a, a) for a in chunk["artifact_ids"])
    return f"[{art}]\n{chunk['text']}" if art else chunk["text"]


def artifact_key(artifact_id: str) -> str:
    """ChromaDB 메타데이터는 목록을 거르기 어려워 유물마다 불리언 키를 둔다: art_A001=True."""
    return f"art_{artifact_id}"


# ---------------------------------------------------------------- 임베딩

class OpenAIEmbedder:
    def __init__(self, model: str, batch_size: int = 64):
        from openai import OpenAI

        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY가 없습니다. agent/retrieval/.env 또는 agent/.env 에 넣어 주세요(.env.example 참고).")
        self.client = OpenAI()
        self.model = model
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for i in range(0, len(texts), self.batch_size):
            res = self.client.embeddings.create(model=self.model, input=texts[i:i + self.batch_size])
            out += [d.embedding for d in res.data]
        return out


class HashEmbedder:
    """테스트용: 글자 2-gram을 해시해 만든 벡터. API 키·네트워크 없이 파이프라인을 확인할 때 쓴다."""

    DIM = 512

    def __init__(self, *_, **__):
        pass

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = []
        for t in texts:
            v = [0.0] * self.DIM
            s = re.sub(r"\s+", "", t)
            for i in range(len(s) - 1):
                h = int(hashlib.md5(s[i:i + 2].encode()).hexdigest(), 16)
                v[h % self.DIM] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            vecs.append([x / n for x in v])
        return vecs


def make_embedder(cfg: dict):
    emb = cfg["embedding"]
    backends = {"openai": OpenAIEmbedder, "hash": HashEmbedder}
    if emb["backend"] not in backends:
        raise SystemExit(f"알 수 없는 embedding.backend: {emb['backend']} (openai | hash)")
    return backends[emb["backend"]](emb["model"], emb.get("batch_size", 64))


# ---------------------------------------------------------------- BM25 토크나이저

@lru_cache(maxsize=1)
def _kiwi(user_words: tuple = ()):
    from kiwipiepy import Kiwi

    kiwi = Kiwi()
    for w in user_words:
        kiwi.add_user_word(w, "NNG", 3)
    return kiwi


def tokenize(text: str, bm25_cfg: dict) -> list[str]:
    """kiwi 형태소 분석으로 내용어만 남긴다. '금관의'·'금관은' → '금관'."""
    keep = bm25_cfg["keep_tags"]
    kiwi = _kiwi(tuple(bm25_cfg.get("user_words", [])))
    return [t.form.lower() for t in kiwi.tokenize(text) if any(t.tag.startswith(k) for k in keep)]


def query_tokens(query: str, bm25_cfg: dict) -> list[str]:
    """질의 BM25 토큰 = 내용어 + 동의어.

    동의어는 품사와 관계없이 모든 형태소에서 찾는다. kiwi가 '만드는'의 '만들'을 보조용언(VX)으로,
    '언제'를 부사(MAG)로 잘라 내용어에서 빠져도 동의어(제작·세기 등)는 붙도록.
    """
    syn = bm25_cfg.get("synonyms") or {}
    kiwi = _kiwi(tuple(bm25_cfg.get("user_words", [])))
    forms = dict.fromkeys(t.form.lower() for t in kiwi.tokenize(query))
    return tokenize(query, bm25_cfg) + [s for f in forms for s in syn.get(f, [])]
