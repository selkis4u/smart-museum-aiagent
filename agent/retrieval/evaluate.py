"""검색 평가(NFR-17): 질의 20건(유물 4점 × 5건).

사용법
  python evaluate.py               # config.yaml 설정 그대로
  python evaluate.py --no-rerank   # Re-ranking 끄고 비교
  python evaluate.py --config other.yaml   # 다른 설정 파일로 비교

판정
  - 통과: 유물로 거른 검색의 상위 3개에 expected 중 하나라도 있음 → 목표 90% 이상(18/20)
  - 혼입: 거른 검색 상위 3개에 그 유물에 연결되지 않은 청크나 distractors가 있음 → 목표 0건
  - 혼동(참고): 거르지 않은 검색 상위 3개에 distractors가 들어온 수. 필터가 없을 때 위험도를 보여 줌
결과는 eval_results/<시각>_<설정>.json 으로 남는다(.gitignore 대상 아님 - 비교 기록용).
"""

import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from common import HERE, load_config, load_jsonl
from retriever import Retriever


def main():
    cfg_path = Path(sys.argv[sys.argv.index("--config") + 1]) if "--config" in sys.argv else None
    cfg = load_config(cfg_path)
    no_rerank = "--no-rerank" in sys.argv
    r = Retriever(cfg, rerank=False if no_rerank else None)
    queries = load_jsonl(cfg["eval_queries"])
    top_k = 3

    rows, lat = [], []
    for q in queries:
        aid = q["artifact_id"]
        t0 = time.perf_counter()
        hits = r.search(aid, q["query"], top_k)
        lat.append(time.perf_counter() - t0)
        got = [h["chunk_id"] for h in hits]
        passed = any(e in got for e in q["expected"])
        mixed = [h["chunk_id"] for h in hits if aid not in h["artifact_ids"] or h["chunk_id"] in q.get("distractors", [])]
        open_hits = [h["chunk_id"] for h in r.search(None, q["query"], top_k)]
        confused = [c for c in open_hits if c in q.get("distractors", [])]
        rows.append({"qid": q["qid"], "artifact_id": aid, "type": q["type"], "query": q["query"],
                     "expected": q["expected"], "top3": got, "kinds": [h["kind"] for h in hits],
                     "pass": passed, "mixed": mixed, "open_top3": open_hits, "open_confused": confused})
        mark = "O" if passed else "X"
        print(f"{mark} {q['qid']} {aid} {q['type']:9} {q['query'][:28]:30} → {', '.join(got)}"
              + (f"  혼입 {mixed}" if mixed else "") + ("" if passed else f"  (정답 {q['expected']})"))

    n = len(rows)
    n_pass = sum(r_["pass"] for r_ in rows)
    n_mixed = sum(len(r_["mixed"]) for r_ in rows)
    n_conf = sum(len(r_["open_confused"]) for r_ in rows)
    setting = f"{cfg['embedding']['backend']}:{cfg['embedding']['model']}" + \
              ("" if no_rerank or not cfg["reranker"]["enabled"] else f" + {cfg['reranker']['model']}")
    summary = {
        "setting": setting,
        "pass": f"{n_pass}/{n} ({n_pass / n:.0%})", "pass_goal_met": n_pass / n >= 0.9,
        "mixed_count": n_mixed, "mixed_goal_met": n_mixed == 0,
        "open_confused_count": n_conf,
        "latency_sec": {"mean": round(statistics.mean(lat), 3), "max": round(max(lat), 3)},
        "by_artifact": {a: f"{sum(x['pass'] for x in rows if x['artifact_id'] == a)}/"
                           f"{sum(1 for x in rows if x['artifact_id'] == a)}"
                        for a in sorted({x["artifact_id"] for x in rows})},
    }
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))

    out_dir = HERE / "eval_results"
    out_dir.mkdir(exist_ok=True)
    tag = ("norerank" if no_rerank or not cfg["reranker"]["enabled"] else "rerank")
    out = out_dir / f"{datetime.now():%Y%m%d_%H%M}_{cfg['embedding']['backend']}_{tag}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
