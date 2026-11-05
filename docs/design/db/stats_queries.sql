-- FR-WEB-11 통계표 쿼리 예시 (SQLite). 기간 필터(FR-WEB-10)는 WHERE started_at BETWEEN :from AND :to 를 붙인다.

-- 1. 유물별 침범 횟수(주의·경고 구분, 최고 단계 기준)
SELECT a.artifact_id, a.name,
       SUM(CASE WHEN i.max_level = 'CAUTION' THEN 1 ELSE 0 END) AS caution_count,
       SUM(CASE WHEN i.max_level = 'WARNING' THEN 1 ELSE 0 END) AS warning_count
FROM artifacts a LEFT JOIN intrusion_records i ON i.artifact_id = a.artifact_id
GROUP BY a.artifact_id ORDER BY a.artifact_id;

-- 2. 시간대별(1시간) 침범 횟수
SELECT strftime('%H', started_at) AS hour, COUNT(*) AS intrusion_count
FROM intrusion_records GROUP BY hour ORDER BY hour;

-- 3. 유물별 평균 침범 지속 시간(초, 닫힌 기록만)
SELECT artifact_id, ROUND(AVG(duration_ms) / 1000.0, 1) AS avg_duration_sec, COUNT(*) AS closed_count
FROM intrusion_records WHERE ended_at IS NOT NULL GROUP BY artifact_id;

-- 4. 유물별 관람 횟수(세션 수)와 평균 청취 인원·끝까지 들은 비율(FR-WEB-15)
SELECT artifact_id, COUNT(*) AS session_count,
       ROUND(AVG(start_count), 1) AS avg_start_count,
       ROUND(1.0 * SUM(completed_count) / NULLIF(SUM(start_count), 0), 2) AS completed_ratio
FROM docent_sessions GROUP BY artifact_id;

-- 5. 유물별·시간대별 규칙 위반 횟수
SELECT artifact_id, strftime('%H', occurred_at) AS hour, COUNT(*) AS violation_count
FROM violation_records GROUP BY artifact_id, hour ORDER BY artifact_id, hour;
