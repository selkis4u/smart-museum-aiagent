"""웹 글(큐레이터 추천 등)을 문단 단위로 나눠 RAG 청크로 만든다.

사용법
  python text_collect.py sources/curator_a003.json

동작
  1) 설정 파일의 file(텍스트 파일)을 줄 단위로 읽는다. 한 줄이 한 문단이다.
  2) 설정의 paragraphs에 적은 시작 문구로 문단을 찾아 종류(kind)와 연결 유물(artifact_ids)을 붙인다.
     headings에 적은 줄은 소제목으로 보고 이후 문단의 section으로 쓴다.
     설정에 없는 줄(사진 설명·사진 저작권 표시 등)은 버리고 목록을 출력한다.
  3) 문단이 길면 문장 경계에서 나누되 글자는 고치지 않는다(공공누리 3유형 변경금지).
  4) data/chunks_<source_id>.jsonl에 저장하고 data/chunks.jsonl(전체)을 다시 합친다.
"""

import json
import re
import sys
from pathlib import Path

from emuseum_collect import ROOT, TARGETS_FILE, merge_chunks, write_jsonl

TEXT_CHUNK_MAX = 350


def target_ids() -> set:
    """targets.json에서 role이 target인 artifact_id 목록."""
    rows = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    return {r["artifact_id"] for r in rows if r.get("role") == "target"}


def split_verbatim(text: str, max_len: int = TEXT_CHUNK_MAX) -> list[str]:
    """문장 끝('다.' 등) 뒤 공백에서만 나눠 원문 글자를 그대로 둔다."""
    if len(text) <= max_len:
        return [text]
    sentences = re.split(r"(?<=[다요]\.)\s+", text)
    chunks, buf = [], ""
    for s in sentences:
        if buf and len(buf) + 1 + len(s) > max_len:
            chunks.append(buf)
            buf = s
        else:
            buf = f"{buf} {s}" if buf else s
    if buf:
        chunks.append(buf)
    return chunks


def build(cfg_path: Path):
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    path = ROOT / cfg["file"]
    if not path.exists():
        sys.exit(f"원문 파일이 없습니다: {path}")
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    targets = target_ids()
    rules = cfg["paragraphs"]
    headings = set(cfg.get("headings", []))

    rows, skipped, used, section = [], [], set(), cfg.get("first_section", "")
    for ln in lines:
        if ln in headings:
            section = ln
            continue
        rule = next((r for r in rules if ln.startswith(r["starts"])), None)
        if rule is None or rule["starts"] in used:  # 설정에 없는 줄, 같은 줄 반복(사진 설명 중복)
            skipped.append(ln)
            continue
        used.add(rule["starts"])
        ids = rule["artifact_ids"]
        role = "target" if targets & set(ids) else "distractor"
        source = {k: cfg[k] for k in ("org", "title", "author", "url", "license", "caution") if k in cfg}
        source["section"] = section
        for piece in split_verbatim(ln):
            rows.append({"chunk_id": f"{cfg['source_id']}-{len(rows) + 1:03d}", "artifact_ids": ids,
                         "role": role, "kind": rule.get("kind", "desc"), "text": piece, "source": source})
        print(f"{rule.get('kind', 'desc'):10} {str(ids):12} {ln[:30]}")

    missing = [r["starts"] for r in rules if r["starts"] not in used]
    if missing:
        sys.exit(f"설정의 문단을 원문에서 찾지 못함: {missing}")
    print(f"\n버린 줄 {len(skipped)}개:")
    for ln in skipped:
        print(f"  - {ln[:60]}")
    out = ROOT / "data" / f"chunks_{cfg['source_id'].lower()}.jsonl"
    write_jsonl(out, rows)
    print(f"\n저장: {out} ({len(rows)}개)")
    merge_chunks()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
    else:
        build(Path(sys.argv[1]))
