"""Web 유물 DB 초기 데이터 내보내기 (FR-WEB-02, 인터페이스 명세 8장).

data/raw의 e뮤지엄 응답에서 등록 유물 4점(A001~A004)의 기본 정보를 뽑아
docs/interface/samples/artifacts_seed.json으로 저장한다. 오프라인으로 돈다(API 키 불필요).

    python export_artifacts.py

e뮤지엄 응답에 없는 값(전시 형태·시연 역할·제작 연도)은 아래 EXTRA에 두며
근거는 docs/requirements/decisions.md다. 이미지 URL은 인증키가 섞여 있어 넣지 않는다.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw"
OUT = HERE.parent.parent / "docs" / "interface" / "samples" / "artifacts_seed.json"

# 표시 이름은 agent/retrieval/config.yaml evidence_cache.artifacts와 같게 둔다
EXTRA = {
    "A001": {"name": "금령총 금관", "display_kind": "SHOWCASE", "role": "DEMO", "era_detail": None},
    "A002": {"name": "지장암 목조비로자나불좌상", "display_kind": "OPEN", "role": "DEMO", "era_detail": "1622년"},
    "A003": {"name": "백자 상감 연꽃 넝쿨무늬 대접", "display_kind": "SHOWCASE", "role": "SPARE", "era_detail": "15~16세기경"},
    "A004": {"name": "「천흥사」가 새겨진 천흥사 동종", "display_kind": "OPEN", "role": "SPARE", "era_detail": "1010년"},
}


def raw_data(emuseum_id):
    path = next(RAW.glob(f"*_{emuseum_id}.json"))
    return json.loads(path.read_text(encoding="utf-8"))["result"]["list"]["data"]


def material(d):
    names = [d.get("materialName1"), d.get("materialName2")]
    return " > ".join(n for n in names if n) or None


def collection_no(d):
    return f"{d['museumName3']}{d['relicNo']}"


def main():
    targets = json.loads((HERE / "targets.json").read_text(encoding="utf-8"))
    artifacts = {}
    for t in targets:
        if t["role"] != "target":
            continue
        d = raw_data(t["emuseum_id"])
        aid = t["artifact_id"]
        if "chunk_prefix" in t:  # 부속 소장품(A002 복장물): 등록하지 않고 본 유물의 참고 정보로만
            artifacts[aid]["related_items"].append({
                "collection_no": collection_no(d), "emuseum_id": d["id"], "name": d["nameKr"],
                "designation": d.get("designationInfo"),
            })
            continue
        extra = EXTRA[aid]
        artifacts[aid] = {
            "artifact_id": aid,
            "collection_no": collection_no(d),
            "emuseum_id": d["id"],
            "name": extra["name"],
            "name_official": d["name"],
            "era": d.get("nationalityName2"),
            "era_detail": extra["era_detail"],
            "museum": d.get("museumName2"),
            "designation": d.get("designationInfo"),
            "material": material(d),
            "size": d.get("sizeInfo"),
            "author": (d.get("author") or "").strip() or None,
            "description": (d.get("desc") or "").strip(),
            "display_kind": extra["display_kind"],
            "role": extra["role"],
            "related_items": [],
        }
    out = {
        "version": 1,
        "source": "e뮤지엄 소장품 정보(국립중앙박물관), agent/knowledge/export_artifacts.py로 생성",
        "artifacts": [artifacts[k] for k in sorted(artifacts)],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{OUT} 저장: 유물 {len(out['artifacts'])}점")


if __name__ == "__main__":
    main()
