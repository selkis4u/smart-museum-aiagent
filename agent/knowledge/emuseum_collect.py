"""e뮤지엄 소장품 Open API로 유물 정보를 받아 RAG 청크(JSONL)로 만드는 스크립트.

사용법
  1) .env 파일에 EMUSEUM_API_KEY=발급받은_일반_인증키(Decoding) 입력
  2) 후보 검색:   python emuseum_collect.py search 금관
                  python emuseum_collect.py search 석조비로자나불좌상
  3) 검색 결과의 id를 targets.json에 artifact_id와 함께 적기
     (id 대신 "relic": "구10416", "search": "지장암"을 적으면 build가 id를 찾아 채운다)
  4) 수집·청킹:   python emuseum_collect.py build
     청크만 다시:   python emuseum_collect.py build --offline   (저장된 data/raw 원본 사용)

결과
  data/raw/<artifact_id>_<id>.json   API 상세 응답 원본
  data/chunks_emuseum.jsonl          API 해설 청크
  data/chunks.jsonl                  모든 출처(chunks_*.jsonl)를 합친 최종 청크
                                     (artifact_ids, 출처, 이용 조건 포함)

주의
  - 상세 조회 파라미터는 id로 가정했다. 첫 실행 때 data/raw 원본을 열어 필드명을 확인할 것.
  - 응답은 Accept 헤더로 JSON을 요청한다. XML이 오면 원본만 저장하고 멈춘다.
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


# 공공데이터포털 '국립중앙박물관_e뮤지엄_박물관 소장품 정보' 주소 (e뮤지엄 OPEN API 이용가이드 기준)
BASE = "https://apis.data.go.kr/1371027/openapi"
HEADERS = {"Accept": "application/json"}
ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
CHUNK_FILE = ROOT / "data" / "chunks.jsonl"            # 모든 출처를 합친 최종 파일
EMUSEUM_CHUNK_FILE = ROOT / "data" / "chunks_emuseum.jsonl"
TARGETS_FILE = ROOT / "targets.json"

CHUNK_MIN, CHUNK_MAX = 80, 220  # 문장 단위로 묶는 길이(자). 해설문 하나가 2~4청크가 되도록


def api_key() -> str:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    key = os.getenv("EMUSEUM_API_KEY")
    if not key:
        sys.exit(".env에 EMUSEUM_API_KEY가 없습니다.")
    return key


def mask_key(obj, key: str):
    """응답 원본을 출력·저장할 때 인증키를 가린다(NFR-11)."""
    if isinstance(obj, dict):
        return {k: mask_key(v, key) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_key(v, key) for v in obj]
    if isinstance(obj, str) and key in obj:
        return obj.replace(key, "***")
    return obj


def xml_to_dict(elem):
    """XML을 dict로 바꾼다. 같은 이름의 자식이 여러 개면 list로 묶는다."""
    children = list(elem)
    if not children:
        if elem.attrib and not (elem.text or "").strip():
            return dict(elem.attrib)
        return (elem.text or "").strip()
    # <item key="nameKr" value="금관"/> 묶음 형식 → {"nameKr": "금관"}
    if all(c.tag.split("}")[-1] == "item" and "key" in c.attrib for c in children):
        return {c.attrib["key"]: c.attrib.get("value", (c.text or "").strip()) for c in children}
    out = {}
    for child in children:
        tag = child.tag.split("}")[-1]
        val = xml_to_dict(child)
        if tag in out:
            if not isinstance(out[tag], list):
                out[tag] = [out[tag]]
            out[tag].append(val)
        else:
            out[tag] = val
    for k, v in elem.attrib.items():  # 속성으로 값이 오는 형식 대응
        out.setdefault(k, v)
    return out


def find_value(obj, names):
    """중첩 구조 어디에 있든 첫 번째로 나오는 해당 키의 값을 찾는다."""
    if isinstance(obj, dict):
        for n in names:
            if n in obj and isinstance(obj[n], (str, int)):
                return str(obj[n])
        for v in obj.values():
            found = find_value(v, names)
            if found:
                return found
    if isinstance(obj, list):
        for v in obj:
            found = find_value(v, names)
            if found:
                return found
    return ""


def call(path: str, **params) -> dict:
    import requests
    key = api_key()
    params["serviceKey"] = key
    try:
        res = requests.get(f"{BASE}{path}", params=params, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        # 오류 메시지에 요청 주소(인증키 포함)가 들어 있어 가린다
        sys.exit(f"API 서버 접속 실패: {type(e).__name__}: {str(e).replace(key, '***')}")
    text = res.text.replace(key, "***")
    dump = RAW_DIR / "last_response.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text(text, encoding="utf-8", newline="\n")  # 마지막 응답 원본은 항상 남긴다

    try:
        data = mask_key(res.json(), key)
    except ValueError:
        try:
            root = ET.fromstring(res.content)
        except ET.ParseError:
            sys.exit(f"JSON도 XML도 아닌 응답입니다(HTTP {res.status_code}). 원본: {dump}")
        data = mask_key({root.tag.split('}')[-1]: xml_to_dict(root)}, key)

    # 공공데이터포털 게이트웨이 인증 오류(XML) 형식
    auth_msg = find_value(data, ["returnAuthMsg"])
    if auth_msg and auth_msg != "NORMAL_SERVICE":
        reason = find_value(data, ["returnReasonCode"])
        sys.exit(f"인증 오류 {reason}: {auth_msg}\n"
                 "  - SERVICE_KEY_IS_NOT_REGISTERED_ERROR: 키 미등록/활성화 대기(1~2시간) 또는 Encoding 키 사용\n"
                 "  - SERVICE ACCESS DENIED: 이 서비스 활용신청이 안 됨")
    code = find_value(data, ["resultCode"])
    if code and code not in ("0", "00", "0000", "200"):
        msg = find_value(data, ["resultMsg"])
        sys.exit(f"API 오류 {code}: {msg} (원본: {dump})")
    if res.status_code >= 400:
        sys.exit(f"HTTP {res.status_code} 오류. 원본: {dump}")
    return data


def find_records(obj):
    """응답 구조가 문서와 달라도 유물 레코드 목록을 찾아낸다."""
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        if any(k in obj[0] for k in ("id", "nameKr", "relicNo")):
            return obj
    if isinstance(obj, dict):
        if any(k in obj for k in ("nameKr", "relicNo")):
            return [obj]
        for v in obj.values():
            found = find_records(v)
            if found:
                return found
    return []


def museum_of(rec: dict) -> str:
    return " ".join(str(rec.get(k, "")) for k in ("museumName1", "museumName2", "museumName3")).strip()


def search(keyword: str, rows: int = 50):
    data = call("/list", name=keyword, numOfRows=rows, pageNo=1)
    recs = find_records(data)
    if not recs:
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
        sys.exit("결과가 없거나 응답 구조를 읽지 못했습니다. 위 원본을 확인하세요.")
    photos = [r for r in recs if "건판" in museum_of(r)]  # 유리건판 사진은 유물이 아님
    recs = [r for r in recs if r not in photos]
    print(f"'{keyword}' 검색 {len(recs)}건 (국립중앙박물관 소장품에 * 표시, 유리건판 사진 {len(photos)}건 제외)\n")
    for r in recs:
        mark = "*" if "국립중앙박물관" in museum_of(r) else " "
        relic_no = f"{r.get('relicNo', '')}-{r.get('relicSubNo', '')}".strip("-")
        print(f"{mark} id={r.get('id')}  {r.get('nameKr')}  [{museum_of(r)}]  {relic_no}")


def pick_description(rec: dict) -> str:
    """해설 본문. e뮤지엄 상세 응답의 해설 필드는 desc다(2026-11-02 실제 응답으로 확인).
    해설이 없는 유물도 있으므로, 없으면 빈 문자열을 돌려주고 기본 정보 청크만 만든다."""
    text = rec.get("desc")
    return text if isinstance(text, str) else ""


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)  # HTML 태그
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[다요음됨함])\.\s+|(?<=\.)\s+(?=[가-힣A-Z])", text)
    return [p.strip() if p.strip().endswith(".") else p.strip() + "." for p in parts if p.strip()]


def chunk_text(text: str, max_len: int = CHUNK_MAX) -> list[str]:
    chunks, buf = [], ""
    for s in split_sentences(text):
        if buf and len(buf) + len(s) > max_len:
            chunks.append(buf)
            buf = s
        else:
            buf = f"{buf} {s}".strip()
    if buf:
        if chunks and len(buf) < CHUNK_MIN:
            chunks[-1] = f"{chunks[-1]} {buf}"
        else:
            chunks.append(buf)
    return chunks


def meta_chunk(rec: dict) -> str:
    """기본 정보도 검색되도록 한 청크로 만든다(이름·시대·재질·크기·출토지 질문 대응)."""
    def join(*keys, sep=" "):
        return sep.join(str(rec[k]) for k in keys if rec.get(k))

    fields = [
        ("이름", rec.get("nameKr", "")),
        ("다른 이름", rec.get("nameCn", "")),            # 예: 보물 금령총 금관(1963), 金鈴塚 金冠
        ("지정", rec.get("designationInfo", "")),
        ("국적/시대", join("nationalityName1", "nationalityName2", sep=" - ")),
        ("재질", join("materialName1", "materialName2", sep=" - ")),
        ("분류", join("purposeName1", "purposeName2", "purposeName3", "purposeName4", sep=" > ")),
        ("크기", rec.get("sizeInfo", "")),
        ("출토지", join("placeLandName1", "placeLandName2")),
        ("소장", join("museumName2", "museumName3") + (f" {rec['relicNo']}" if rec.get("relicNo") else "")),
        ("색인어", rec.get("indexWord", "")),
    ]
    return " / ".join(f"{label}: {val}" for label, val in fields if val)


def resolve_id(t: dict) -> str:
    """targets의 'relic'(예: 구10416)과 'search'(검색어)로 e뮤지엄 id를 찾는다."""
    m = re.match(r"^(\D*)(\d+)$", t["relic"].replace(" ", ""))
    if not m:
        sys.exit(f"{t['artifact_id']}: relic 형식이 잘못됨 ({t['relic']}). 예: 구10416")
    prefix, num = m.groups()
    recs = find_records(call("/list", name=t["search"], numOfRows=100, pageNo=1))
    hits = [r for r in recs if str(r.get("relicNo")) == num and str(r.get("museumName3", "")).startswith(prefix)
            and "국립중앙박물관" in museum_of(r)]
    if len(hits) != 1:
        found = [f"{r.get('museumName3')}{r.get('relicNo')} {r.get('nameKr')}" for r in recs][:10]
        sys.exit(f"{t['artifact_id']}: '{t['search']}' 검색에서 {t['relic']}을 하나로 찾지 못함 ({len(hits)}건). 검색 결과: {found}")
    print(f"{t['artifact_id']}: {t['relic']} → id {hits[0]['id']}")
    return hits[0]["id"]


def build(offline: bool = False):
    """offline=True면 API를 부르지 않고 data/raw에 저장된 원본으로 청크만 다시 만든다."""
    if not TARGETS_FILE.exists():
        sys.exit("targets.json이 없습니다. search로 id를 찾은 뒤 작성하세요.")
    targets = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    changed = False
    for t in targets:
        if not t.get("emuseum_id"):
            if offline:
                print(f"[건너뜀] {t['artifact_id']} id 미확정 → 온라인 build 필요")
                continue
            t["emuseum_id"] = resolve_id(t)
            changed = True
        # 한 유물에 딸린 소장품(조성기·복장물 등)은 chunk_prefix로 구분한다(예: A002R1)
        prefix = t.get("chunk_prefix", t["artifact_id"])
        raw_path = RAW_DIR / f"{prefix}_{t['emuseum_id']}.json"
        if offline:
            if not raw_path.exists():
                print(f"[건너뜀] {prefix} 원본 없음 → 온라인 build 필요 ({t.get('memo', '')})")
                continue
            data = json.loads(raw_path.read_text(encoding="utf-8"))
        else:
            data = call("/detail", id=t["emuseum_id"])
            raw_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        recs = find_records(data)
        if not recs:
            print(f"[경고] {t['artifact_id']} 상세 응답을 읽지 못함 → data/raw 원본 확인")
            continue
        rec = recs[0]
        source = {
            "org": rec.get("museumName2") or "국립중앙박물관",
            "title": f"e뮤지엄 소장품 상세 - {rec.get('nameKr', '')}",
            "emuseum_id": t["emuseum_id"],
            "license": t.get("license", "공공누리 제1유형(출처표시)"),
        }
        pieces = [("meta", meta_chunk(rec))]
        pieces += [("desc", c) for c in chunk_text(clean(pick_description(rec)))]
        for i, (kind, text) in enumerate(pieces, 1):
            if not text:
                continue
            out.append({
                "chunk_id": f"{prefix}-{i:02d}",
                "artifact_ids": [t["artifact_id"]],  # 한 청크가 여러 유물에 걸칠 수 있어 목록으로 둔다
                "role": t.get("role", "target"),  # target | distractor(혼동 테스트용)
                "kind": kind,
                "text": text,
                "source": source,
            })
        note = "" if len(pieces) > 1 else "  (해설 없음, 기본 정보만)"
        print(f"{prefix:6} {rec.get('nameKr')}: 청크 {len(pieces)}개{note}")
    if changed:  # 소장품번호로 찾은 id를 targets.json에 적어 둔다
        TARGETS_FILE.write_text(json.dumps(targets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("targets.json에 찾은 id를 저장했습니다.")
    write_jsonl(EMUSEUM_CHUNK_FILE, out)
    print(f"\n저장: {EMUSEUM_CHUNK_FILE} ({len(out)}개)")
    merge_chunks()


def write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")


def merge_chunks():
    """data/chunks_*.jsonl(출처별 청크)을 모아 data/chunks.jsonl 하나로 만든다."""
    rows = []
    for f in sorted(CHUNK_FILE.parent.glob("chunks_*.jsonl")):
        part = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows += part
        print(f"  합치기: {f.name} {len(part)}개")
    ids = [r["chunk_id"] for r in rows]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        sys.exit(f"chunk_id 중복: {sorted(dup)[:5]}")
    write_jsonl(CHUNK_FILE, rows)
    print(f"최종: {CHUNK_FILE} ({len(rows)}개)")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "search":
        search(" ".join(sys.argv[2:]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "build":
        build(offline="--offline" in sys.argv)
    else:
        print(__doc__)
