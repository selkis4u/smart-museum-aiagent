"""CV → Agent 이벤트 DTO 검사기 (interface_spec 2장).

사용법:
    pip install jsonschema
    python validate_cv_events.py ../samples/cv_events_scenario.jsonl
    python validate_cv_events.py my_events.jsonl      # CV 로그(한 줄에 이벤트 1개)

JSON 스키마(필드·형식·종류별 규칙)와 스키마로 표현하기 어려운 규칙
(단계 변화, seq 연속, event_id 중복, 구역별 단계 이어짐)을 함께 검사한다.
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = json.loads((Path(__file__).parent / "cv_event.schema.json").read_text(encoding="utf-8"))


def check(lines):
    validator = Draft202012Validator(SCHEMA)
    errors, seen_ids, zone_level, last_seq = [], set(), {}, None
    for no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"{no}행: JSON 아님 ({e})")
            continue
        schema_errors = sorted(validator.iter_errors(ev), key=lambda e: list(e.path))
        for e in schema_errors:
            field = ".".join(map(str, e.path)) or "(전체)"
            errors.append(f"{no}행 {field}: {e.message}")
        if schema_errors:
            # 뒤 이벤트에 엉뚱한 오류가 이어지지 않도록 쓸 수 있는 값만 이어받는다
            if isinstance(ev.get("seq"), int):
                last_seq = ev["seq"]
            if ev.get("level") in ("NORMAL", "CAUTION", "WARNING") and isinstance(ev.get("zone_id"), str):
                zone_level[ev["zone_id"]] = ev["level"]
            continue

        if ev["event_id"] in seen_ids:
            errors.append(f"{no}행: event_id 중복 {ev['event_id']}")
        seen_ids.add(ev["event_id"])

        if last_seq is not None and ev["seq"] != last_seq + 1 and ev["seq"] != 1:
            errors.append(f"{no}행: seq {last_seq} 다음이 {ev['seq']} (누락 또는 순서 뒤바뀜, 재연결이면 1부터)")
        last_seq = ev["seq"]

        zone = ev["zone_id"]
        if ev["type"] == "LEVEL_CHANGE":
            if ev["prev_level"] == ev["level"]:
                errors.append(f"{no}행: LEVEL_CHANGE인데 prev_level·level이 같음 ({ev['level']})")
        elif ev["prev_level"] != ev["level"]:
            errors.append(f"{no}행: {ev['type']}는 prev_level·level에 현재 단계를 같은 값으로 넣어야 함")

        known = zone_level.get(zone)
        if known is not None and ev["prev_level"] != known:
            errors.append(f"{no}행: {zone} 직전 단계는 {known}인데 prev_level이 {ev['prev_level']}")
        zone_level[zone] = ev["level"]
    return errors


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
    errors = check(lines)
    if errors:
        print("\n".join(errors))
        sys.exit(f"실패: {len(errors)}건")
    print(f"통과: 이벤트 {sum(1 for l in lines if l.strip())}건")


if __name__ == "__main__":
    main()
