"""Oracle 스키마 검증 (docs/design/db/schema_draft.sql·stats_queries.sql).

빈 계정에 테이블을 만들고(같은 이름 테이블이 있으면 지우고 다시 만듦) 유물 4점 초기 데이터와
가짜 기록을 넣은 뒤, 제약 5종과 통계 쿼리 5개를 확인한다. 시연용 계정에는 돌리지 말 것.

    pip install oracledb
    set ORACLE_DSN=127.0.0.1:1521/FREEPDB1
    set ORACLE_USER=museum
    set ORACLE_PASSWORD=...
    python docs/design/db/check_oracle.py     (저장소 최상위에서 실행)
"""
import os
import json, datetime as dt
import oracledb
con = oracledb.connect(user=os.environ.get("ORACLE_USER", "museum"), password=os.environ["ORACLE_PASSWORD"],
                       dsn=os.environ.get("ORACLE_DSN", "127.0.0.1:1521/FREEPDB1"))
def ts_handler(cursor, value, arraysize):   # datetime을 TIMESTAMP로 보내 밀리초 유지
    if isinstance(value, dt.datetime):
        return cursor.var(oracledb.DB_TYPE_TIMESTAMP, arraysize=arraysize)
con.inputtypehandler = ts_handler
cur = con.cursor()
print("Oracle", con.version)

def stmts(path):
    sql = open(path, encoding="utf-8").read()
    sql = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return [s.strip() for s in sql.split(";") if s.strip()]

for t in ["violation_records","docent_sessions","intrusion_records","artifact_related_items","artifacts","admin_users"]:
    try: cur.execute(f"DROP TABLE {t} CASCADE CONSTRAINTS PURGE")
    except oracledb.DatabaseError: pass
for s in stmts("docs/design/db/schema_draft.sql"):
    cur.execute(s)
print("DDL 실행 OK:", len(stmts("docs/design/db/schema_draft.sql")), "문")

seed = json.load(open("docs/interface/samples/artifacts_seed.json", encoding="utf-8"))
cols = ["artifact_id","collection_no","emuseum_id","name","name_official","era","era_detail","museum",
        "designation","material","size_info","author","description","display_kind","role"]
for a in seed["artifacts"]:
    row = dict(a, size_info=a["size"])
    cur.execute(f"INSERT INTO artifacts ({','.join(cols)}) VALUES ({','.join(':'+c for c in cols)})",
                {c: row[c] for c in cols})
    for r in a["related_items"]:
        cur.execute("INSERT INTO artifact_related_items (artifact_id,collection_no,emuseum_id,name,designation) VALUES (:1,:2,:3,:4,:5)",
                    (a["artifact_id"], r["collection_no"], r["emuseum_id"], r["name"], r["designation"]))
print("유물", cur.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], "점, 부속",
      cur.execute("SELECT COUNT(*) FROM artifact_related_items").fetchone()[0], "건")

T = lambda s: dt.datetime.fromisoformat(s)
ins = """INSERT INTO intrusion_records (event_id,zone_id,artifact_id,start_level,max_level,cause,visitor_ids,
         started_at,ended_at,duration_ms,session_id,session_paused,repeated_caution)
         VALUES (:1,'Z01','A001',:2,:3,:4,:5,:6,:7,:8,'ses-Z01-20261120-140300000',:9,:10) RETURNING record_id INTO :11"""
rid = cur.var(int)
cur.execute(ins, ("evt-20261120-140321123-0002","CAUTION","CAUTION","LINE_1","[3]",T("2026-11-20 14:03:21.123"),None,None,1,0,rid))
r1 = rid.getvalue()[0]
# PATCH 갱신 → 닫기 (명세 4.4)
cur.execute("UPDATE intrusion_records SET max_level='WARNING', cause='CAUTION_TIMEOUT', last_event_id=:ev WHERE record_id=:rid", rid=r1, ev="evt-20261120-140326123-0003")
end = T("2026-11-20 14:03:31.900")
started = cur.execute("SELECT started_at FROM intrusion_records WHERE record_id=:rid", rid=r1).fetchone()[0]
dur = round((end - started).total_seconds() * 1000)   # Flask가 계산(명세 4.4)
cur.execute("UPDATE intrusion_records SET ended_at=:e, visitor_ids=:v, last_event_id=:ev, duration_ms=:d WHERE record_id=:rid",
            e=end, v="[3,5]", ev="evt-20261120-140331900-0004", d=dur, rid=r1)
cur.execute(ins, ("evt-20261120-140335000-0005","CAUTION","WARNING","LINE_2","[5]",T("2026-11-20 14:03:35.000"),T("2026-11-20 14:03:39.000"),4000,1,1,rid))
cur.execute(ins, ("evt-20261120-140350000-0008","WARNING","WARNING","TOUCH","[3]",T("2026-11-20 14:03:50.000"),None,None,1,0,rid))
print("침범 기록 1 지속 ms:", cur.execute("SELECT duration_ms FROM intrusion_records WHERE record_id=:1",[r1]).fetchone()[0])
script = "지금 보고 계신 유물은 금령총 금관입니다. " * 40   # CLOB 한글 긴 글
cur.execute("""INSERT INTO docent_sessions (session_id,zone_id,artifact_id,started_at,ended_at,end_reason,start_count,
               script_end_count,completed_count,script,rag_chunk_ids,source_urls,fallback_used,generation_failed)
               VALUES ('ses-Z01-20261120-140300000','Z01','A001',:1,:2,'LEFT_AFTER_COMPLETE',2,2,1,:3,:4,'[]',0,0)""",
            (T("2026-11-20 14:03:00"), T("2026-11-20 14:06:00"), script, '["A001-03","GC2010-012"]'))
cur.execute("""INSERT INTO violation_records (event_id,zone_id,artifact_id,visitor_id,item_type,occurred_at)
               VALUES ('evt-20261120-140400050-0010','Z02','A002',7,'TAKEOUT_CUP',:1)""", [T("2026-11-20 14:04:00.050")])
con.commit()

bad = {
 "중복 event_id": ("INSERT INTO violation_records (event_id,zone_id,artifact_id,visitor_id,item_type,occurred_at) VALUES ('evt-20261120-140400050-0010','Z02','A002',7,'TAKEOUT_CUP',LOCALTIMESTAMP)", None),
 "없는 유물(D001)": ("INSERT INTO violation_records (event_id,zone_id,artifact_id,visitor_id,item_type,occurred_at) VALUES ('x1','Z02','D001',7,'TAKEOUT_CUP',LOCALTIMESTAMP)", None),
 "틀린 종료 사유": ("INSERT INTO docent_sessions (session_id,zone_id,artifact_id,started_at,ended_at,end_reason,start_count) VALUES ('s1','Z01','A001',LOCALTIMESTAMP,LOCALTIMESTAMP,'DONE',1)", None),
 "JSON 아닌 visitor_ids": ("INSERT INTO intrusion_records (event_id,zone_id,artifact_id,start_level,max_level,visitor_ids,started_at) VALUES ('x2','Z01','A001','CAUTION','CAUTION','3,5',LOCALTIMESTAMP)", None),
 "빈 문자열 이름('' = NULL)": ("INSERT INTO artifacts (artifact_id,collection_no,name,museum,display_kind,role) VALUES ('A099','t1','','m','OPEN','DEMO')", None),
}
for k,(sql,_) in bad.items():
    try: cur.execute(sql); print("!! 통과됨:", k); con.rollback()
    except oracledb.DatabaseError as e: print("막힘:", k, "→", str(e).split("\n")[0][:70])
ok100 = "가"*100
cur.execute("INSERT INTO artifacts (artifact_id,collection_no,name,museum,display_kind,role) VALUES ('A098','t2',:1,'m','OPEN','DEMO')",[ok100]); con.rollback()
print("한글 100자 이름 OK")

for i, q in enumerate(stmts("docs/design/db/stats_queries.sql"), 1):
    print(f"통계 {i}:", cur.execute(q).fetchall())
