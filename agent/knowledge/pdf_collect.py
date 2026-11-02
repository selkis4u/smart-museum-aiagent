"""PDF 자료(강의 자료·도록 등)를 장·절 단위로 나눠 RAG 청크로 만든다.

사용법
  python pdf_collect.py sources/gold_crown_2010.json

동작
  1) 글자 크기로 본문과 각주를 나눈다(본문 11pt, 각주 9pt 등은 설정 파일에 지정).
  2) 장·절 제목으로 단위를 나눈다. 제목 모양(정규식)과 글자 크기는 설정 파일의 headings에 지정한다.
     기본값은 '1. 머리말'(장) / '① 금령총 금관'(절) / '2) 형태 변화'(절 해제) 형식.
  3) 설정 파일의 units에 따라 단위마다 연결할 artifact_ids와 청크 종류를 정한다.
     - kind: "desc"(유물 설명, 기본) 또는 "background"(시대 배경: 이 유물의 사실로 말하지 않음)
     - exclude_if_contains: 이 단어가 들어간 청크는 연결을 끊고 혼동용으로 돌린다
  4) 본문은 desc/background, 각주는 note 청크로 만들어 data/chunks_<source_id>.jsonl에 저장하고
     data/chunks.jsonl(전체)을 다시 합친다.

필요 패키지: pip install pymupdf
"""

import json
import re
import sys
from pathlib import Path

import pymupdf

from emuseum_collect import ROOT, chunk_text, merge_chunks, write_jsonl

PDF_CHUNK_MAX = 350  # 강의 자료는 설명이 길어 API 해설(220자)보다 크게 묶는다
TARGETS = {"A001", "A002"}  # 시연 유물
NOTE_MIN = 50  # 이보다 짧은 각주는 정보가 거의 없어 버린다

DEFAULT_HEADINGS = {
    "chapter": {"pattern": r"^(\d)\.\s+\S", "font_min": 11.5},        # 1. 머리말
    "sub": {"pattern": r"^([①-⑨])\s+[가-힣]", "font": "body"},         # ④ 금령총 금관
    "reset": {"pattern": r"^\d\)\s+\S", "font": "body"},              # 2) 형태 변화 → 절 해제
}
NOTE_START = re.compile(r"^\d{1,2}\)\s")      # 각주 7) 이 무덤에서…
CAPTION = re.compile(r"^\s*(도\s?\d+\.|\*)")   # 도판 설명(도7. / 도 1.)


def strip_note_marks(text: str) -> str:
    """본문 속 각주 번호(금령총(金鈴塚)7), → 금령총(金鈴塚),)를 지운다."""
    text = re.sub(r"<도\s?[\d\s․,~\-]+>", "", text)  # 본문 속 도판 참조 <도 3>, <도 15․16>
    return re.sub(r"(?<=[가-힣A-Za-z\)\]\.,’”>])\d{1,2}\)", "", text)


def lines_of(pdf_path: Path):
    """(쪽 번호, 글자 크기, 줄 텍스트)를 차례로 돌려준다."""
    with pymupdf.open(pdf_path) as doc:
        for pno, page in enumerate(doc, 1):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    # 앞 공백만 지우고 줄 끝 공백은 남긴다: 줄 끝 공백이 있으면 다음 줄과 띄어 쓰는 것
                    text = "".join(s["text"] for s in line["spans"]).lstrip()
                    if text.strip():
                        yield pno, line_size(line["spans"]), text


def line_size(spans) -> float:
    """줄의 글자 크기. 한자처럼 일부 글자만 크기가 다른 줄이 있어, 가장 많은 글자의 크기로 정한다."""
    weight = {}
    for s in spans:
        n = len(s["text"].strip())
        if n:
            size = round(s["size"], 1)
            weight[size] = weight.get(size, 0) + n
    return max(weight, key=weight.get) if weight else 0.0


def compile_headings(cfg: dict) -> dict:
    """설정의 headings를 (정규식, 글자 크기 판정 함수)로 바꾼다."""
    lo, hi = cfg["body_font"]
    out = {}
    for name, spec in {**DEFAULT_HEADINGS, **cfg.get("headings", {})}.items():
        if spec is None:
            continue
        if "font_min" in spec:
            fits = (lambda m: lambda sz: sz >= m)(spec["font_min"])
        elif spec.get("font") == "body":
            fits = lambda sz: lo <= sz <= hi
        else:
            fits = (lambda a, b: lambda sz: a <= sz <= b)(*spec["font"])
        out[name] = (re.compile(spec["pattern"]), fits)
    return out


def parse(cfg: dict, pdf_path: Path) -> dict:
    """단위 키(예: '3-④', 'Ⅳ-2')별로 본문 문단과 각주, 쪽 번호를 모은다."""
    lo, hi = cfg["body_font"]
    nlo, nhi = cfg["note_font"]
    heads = compile_headings(cfg)
    units, chapter, sub = {}, None, None
    note_buf, in_caption = None, False

    def unit():
        key = chapter + (f"-{sub}" if sub else "")
        return units.setdefault(key, {"body": [], "notes": [], "pages": set()})

    def heading(name, text, size):
        if name not in heads:
            return None
        rx, fits = heads[name]
        return rx.match(text) if fits(size) else None

    for pno, size, text in lines_of(pdf_path):
        if cfg["stop_heading"] in text and size > nhi:
            break
        m = heading("chapter", text, size)
        if m:
            chapter, sub = m.group(1), None
            unit()["title"] = text.strip()
            continue
        if chapter is None:
            continue  # 표지·목차·국문요약
        m = heading("sub", text, size)
        if m:
            sub = m.group(1)
            unit()["title"] = text.strip()
            continue
        if heading("reset", text, size):
            sub = None
            unit()["body"].append("\n")  # 소제목은 문단 경계로만 쓴다
            continue

        if lo <= size <= hi:  # 본문
            u = unit()
            u["body"].append(text)
            u["pages"].add(pno)
        elif nlo <= size <= nhi:  # 각주·도판 설명
            if CAPTION.match(text):
                in_caption = True
                continue
            if NOTE_START.match(text):
                in_caption = False
                note_buf = [text]
                unit()["notes"].append(note_buf)
            elif note_buf is not None and not in_caption:
                note_buf.append(text)
    return units


def join_lines(lines: list[str]) -> str:
    """PDF 줄바꿈을 이어 붙인다.
    줄 끝에 공백이 있으면 띄어 쓰고, 없으면 단어 중간에서 줄바꿈된 것('…발굴되' / '었다')으로 보고 붙인다.
    단, 한글이 아닌 글자끼리(숫자·영문)가 맞닿으면 띄운다."""
    out = ""
    for ln in lines:
        if ln != "\n":
            ln = strip_note_marks(ln)
        if ln == "\n":
            out = out.rstrip() + "\n"
            continue
        if not out or out.endswith(("\n", " ")):
            out += ln
        elif out.endswith((".", "?", "!")):
            out += " " + ln  # 쪽이 바뀌는 곳은 줄 끝 공백이 없어도 문장이 끝났으면 띄운다
        elif re.search(r"[가-힣]$", out) or re.match(r"^[가-힣]", ln):
            out += ln
        else:
            out += " " + ln
    return re.sub(r"[ \t]+", " ", out).strip()


def build(cfg_path: Path):
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    pdf_path = ROOT / cfg["file"]
    if not pdf_path.exists():
        sys.exit(f"PDF가 없습니다: {pdf_path}")
    units = parse(cfg, pdf_path)

    rows, seq = [], 0
    for key, u in units.items():
        rule = cfg["units"].get(key)
        if rule is None:
            print(f"[경고] 설정에 없는 단위 {key} ({u.get('title', '')}) → 건너뜀")
            continue
        ids = cfg["common_ids"] if rule["artifact_ids"] == "common" else rule["artifact_ids"]
        role = "target" if TARGETS & set(ids) else "distractor"
        pages = sorted(u["pages"])
        source = {
            "org": cfg["org"], "title": cfg["title"], "author": cfg["author"], "date": cfg["date"],
            "section": u.get("title", key), "pages": f"{pages[0]}-{pages[-1]}" if pages else "",
            "license": cfg["license"], "caution": cfg["caution"],
        }
        kind = rule.get("kind", "desc")
        excl = rule.get("exclude_if_contains", [])
        paragraphs = [p for p in strip_note_marks(join_lines(u["body"])).split("\n") if p.strip()]
        pieces = [(kind, c) for p in paragraphs for c in chunk_text(p, PDF_CHUNK_MAX)]
        notes = [join_lines(n) for n in u["notes"]]
        # 문장이 없는 각주(예: '박형국, 앞의 논문')는 인용 표기라 버린다
        pieces += [(("background" if kind == "background" else "note"), n) for n in notes
                   if re.search(r"다[.)]", n) and len(n) >= NOTE_MIN]
        counts = {}
        for k, text in pieces:
            c_ids, c_role, c_kind = ids, role, k
            if excl and any(w in text for w in excl):
                c_ids, c_role, c_kind = [], "distractor", "desc"  # 다른 유물 이야기라 연결하지 않음
            seq += 1
            rows.append({"chunk_id": f"{cfg['source_id']}-{seq:03d}", "artifact_ids": c_ids, "role": c_role,
                         "kind": c_kind, "text": text, "source": source})
            label = c_kind if c_ids or not ids else "제외→혼동"
            counts[label] = counts.get(label, 0) + 1
        summary = " · ".join(f"{k} {v}" for k, v in counts.items())
        print(f"{key:5} {u.get('title', '')[:20]:22} → {ids or '연결 없음'}  {summary}")

    out = ROOT / "data" / f"chunks_{cfg['source_id'].lower()}.jsonl"
    write_jsonl(out, rows)
    print(f"\n저장: {out} ({len(rows)}개)")
    merge_chunks()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
    else:
        build(Path(sys.argv[1]))
