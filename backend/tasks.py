from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pymysql, pytz


def get_connection():
    conn = pymysql.connect(
        host="database-1.cts2qeeg0ot5.ap-northeast-2.rds.amazonaws.com",
        user="kevin",
        db="vpp_2",
        password="spreatics*",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )
    with conn.cursor() as cursor:
        cursor.execute("SET time_zone = '+09:00'")
    return conn

KST = pytz.timezone("Asia/Seoul")

# 15분 단위 반올림 함수
def round_to_nearest_15min(dt):
    discard = timedelta(minutes=dt.minute % 15,
                        seconds=dt.second,
                        microseconds=dt.microsecond)
    dt -= discard
    if discard >= timedelta(minutes=7.5):
        dt += timedelta(minutes=15)
    return dt

# KST aware datetime → UTC naive datetime 변환 함수 (DB 저장용)
def kst_to_utc_naive(dt_kst):
    return dt_kst.astimezone(pytz.UTC).replace(tzinfo=None)

def evaluate_bids():
    now = datetime.now(KST)
    print(f"[{now}] ⏳ 입찰 평가 시작")

    try:
        conn = get_connection()
        conn.begin()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT bid_id 
                FROM bidding_log 
                WHERE bid_id = (SELECT MAX(bid_id) FROM bidding_log)
                FOR UPDATE
            """)
            row = cursor.fetchone()
            if not row or row["bid_id"] is None:
                print("🚫 평가할 입찰 없음")
                conn.rollback()
                return

            latest_bid_id = row["bid_id"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM bidding_result WHERE bid_id = %s", (latest_bid_id,))
            if cursor.fetchone()["cnt"] > 0:
                print(f"⚠️ 이미 평가된 입찰 batch {latest_bid_id}, 생략")
                conn.rollback()
                return

            rounded_time_kst = round_to_nearest_15min(now)
            rounded_time_utc = kst_to_utc_naive(rounded_time_kst)  # UTC naive 변환

            print(f"KST now: {now}, rounded_time_kst: {rounded_time_kst}, rounded_time_utc: {rounded_time_utc}")

            cursor.execute("SELECT * FROM bidding_log WHERE bid_id = %s", (latest_bid_id,))
            bids = cursor.fetchall()

            # SMP 가격 조회 시 UTC naive datetime 사용
            cursor.execute("SELECT price_krw FROM smp WHERE smp_time = %s", (rounded_time_utc,))
            smp_row = cursor.fetchone()
            print(rounded_time_utc)
            print(smp_row)
            if not smp_row:
                print("❌ SMP 데이터 없음")
                conn.rollback()
                return

            market_price = smp_row["price_krw"]

            accepted_entities = []
            off_targets = set()
            evaluated_entities = []

            for bid in bids:
                entity_id = bid["entity_id"]
                bid_price = bid["bid_price_per_kwh"]
                evaluated_entities.append(entity_id)

                if bid_price is None:
                    result = 'rejected'
                    bid_price_val = None
                else:
                    result = 'accepted' if bid_price <= market_price else 'rejected'
                    bid_price_val = bid_price

                cursor.execute("""
                    INSERT INTO bidding_result (bid_id, entity_id, quantity_kwh, bid_price, result)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    latest_bid_id,
                    entity_id,
                    bid["bid_quantity_kwh"],
                    bid_price_val,
                    result
                ))

                print(f"🔎 평가 결과: entity_id={entity_id}, bid_price={bid_price}, SMP={market_price} → {result}")

                if result == 'accepted':
                    accepted_entities.append(entity_id)
                    if entity_id == 1:
                        off_targets.add(4)
                    elif entity_id == 2:
                        off_targets.add(5)

            # relay_status 업데이트도 UTC naive datetime 사용
            for entity_id in evaluated_entities:
                if entity_id in accepted_entities:
                    cursor.execute("""
                        UPDATE relay_status SET status = 1, last_updated = %s WHERE relay_id = %s
                    """, (rounded_time_utc, entity_id))
                    print(f"🟢 relay ON: {entity_id}")
                else:
                    cursor.execute("""
                        UPDATE relay_status SET status = 0, last_updated = %s WHERE relay_id = %s
                    """, (rounded_time_utc, entity_id))
                    print(f"🔴 relay OFF: {entity_id}")

            for off_id in off_targets:
                cursor.execute("""
                    UPDATE relay_status SET status = 0, last_updated = %s WHERE relay_id = %s
                """, (rounded_time_utc, off_id))
                print(f"⚫ relay FORCE OFF: {off_id} (accepted된 발전소 보호)")

            conn.commit()
            print(f"✅ 입찰 평가 완료: batch {latest_bid_id} (SMP {market_price})")

    except Exception as e:
        conn.rollback()
        print(f"❌ 입찰 평가 오류: {e}")




# 최근 계산 시점 구하기
def get_last_calc_time():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 가장 최신 bid_id
            cursor.execute("SELECT MAX(bid_id) AS latest_bid_id FROM bidding_result")
            row = cursor.fetchone()
            if not row or ndef get_last_calc_time():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT MAX(bid_id) AS latest_bid_id FROM bidding_result")
            row = cursor.fetchone()
            if not row or not row["latest_bid_id"]:
                return datetime.now(KST) - timedelta(hours=1)

            latest_bid_id = row["latest_bid_id"]

            cursor.execute("""
                SELECT br.entity_id, bl.bid_time
                FROM bidding_result br
                JOIN bidding_log bl
                  ON br.bid_id = bl.bid_id AND br.entity_id = bl.entity_id
                WHERE br.bid_id = %s AND br.result = 'accepted'
            """, (latest_bid_id,))
            accepted_rows = cursor.fetchall()

            if not accepted_rows:
                return datetime.now(KST) - timedelta(hours=1)

            bid_time = accepted_rows[0]["bid_time"]
            # DB에서 온 bid_time이 naive면 UTC로 가정 후 KST 변환
            bid_time = utc_naive_to_kst(bid_time)

            bid_apply_time = bid_time + timedelta(minutes=15)

            cursor.execute("SELECT MAX(timestamp) AS last_profit_time FROM profit_log")
            row = cursor.fetchone()
            if row and row["last_profit_time"]:
                last_profit_time = utc_naive_to_kst(row["last_profit_time"])
                return max(last_profit_time, bid_apply_time)
            else:
                return bid_apply_time
    finally:
        conn.close()

def calculate_profit_incremental():
    last_calc_time = get_last_calc_time()
    now = datetime.now(KST)
    print(f"[{now}] ▶ 이전 계산 시점: {last_calc_time}, 현재 시각: {now}")

    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT MAX(bid_id) AS latest_bid_id FROM bidding_result")
            latest_bid_id = cursor.fetchone()["latest_bid_id"]

            if not latest_bid_id:
                print("⚠️ 최신 bid_id 없음, 계산 종료")
                return

            cursor.execute("""
                SELECT br.entity_id, bl.bid_price_per_kwh
                FROM bidding_result br
                JOIN bidding_log bl
                  ON br.bid_id = bl.bid_id AND br.entity_id = bl.entity_id
                WHERE br.bid_id = %s AND br.result = 'accepted'
            """, (latest_bid_id,))
            accepted_bids = cursor.fetchall()
            price_map = {row["entity_id"]: row["bid_price_per_kwh"] for row in accepted_bids}

            if not price_map:
                print("⚠️ accepted 입찰 없음, 계산 종료")
                return

            cursor.execute("SELECT relay_id FROM relay_status WHERE status = 1")
            on_relays = {row["relay_id"] for row in cursor.fetchall()}

            last_calc_time_utc = kst_to_utc_naive(last_calc_time)
            now_utc = kst_to_utc_naive(now)

            for entity_id, unit_price in price_map.items():
                if entity_id not in on_relays:
                    print(f"⛔ entity_id={entity_id} relay OFF → 계산 생략")
                    continue

                cursor.execute("""
                    SELECT node_timestamp, power_kw
                    FROM node_status_log
                    WHERE relay_id = %s
                    AND node_timestamp > %s AND node_timestamp <= %s
                    ORDER BY node_timestamp ASC
                """, (entity_id, last_calc_time_utc, now_utc))
                logs = cursor.fetchall()

                if not logs:
                    print(f"⚠️ 발전 로그 없음: entity_id={entity_id}")
                    continue

                total_revenue = 0
                for i in range(len(logs)):
                    current_log = logs[i]
                    current_time = utc_naive_to_kst(current_log["node_timestamp"])
                    power_kw = current_log["power_kw"]

                    if i < len(logs) - 1:
                        next_time = utc_naive_to_kst(logs[i+1]["node_timestamp"])
                    else:
                        next_time = now

                    time_diff_seconds = (next_time - current_time).total_seconds()
                    revenue = power_kw * unit_price 
                    total_revenue += revenue

                total_revenue = round(total_revenue, 2)
                print(f"✅ entity_id={entity_id} → {len(logs)}개 로그, 수익 {total_revenue}원")

                cursor.execute("""
                    INSERT INTO profit_log (timestamp, entity_id, unit_price, revenue_krw)
                    VALUES (%s, %s, %s, %s)
                """, (now_utc, entity_id, unit_price, total_revenue))

            conn.commit()
            print(f"[{now}] 💾 수익 누적 저장 완료")

    except Exception as e:
        print(f"❌ calculate_profit_incremental 오류: {e}")
    finally:
        conn.close()ot row["latest_bid_id"]:
                return datetime.now(KST) - timedelta(hours=1)

            latest_bid_id = row["latest_bid_id"]

            # 2. 해당 bid_id의 accepted 입찰 + bid_time
            cursor.execute("""
                SELECT br.entity_id, bl.bid_time
                FROM bidding_result br
                JOIN bidding_log bl
                  ON br.bid_id = bl.bid_id AND br.entity_id = bl.entity_id
                WHERE br.bid_id = %s AND br.result = 'accepted'
            """, (latest_bid_id,))
            accepted_rows = cursor.fetchall()

            if not accepted_rows:
                # 최신 시장에 accepted가 없으면 1시간 전부터 계산
                return datetime.now(KST) - timedelta(hours=1)

            # 모든 accepted는 같은 bid_time이라고 가정 → 첫 번째 사용
            bid_time = accepted_rows[0]["bid_time"]
            if bid_time.tzinfo is None:
                bid_time = bid_time.replace(tzinfo=KST)

            bid_apply_time = bid_time + timedelta(minutes=15)

            # 3. profit_log 최신 계산 시각 확인
            cursor.execute("SELECT MAX(timestamp) AS last_profit_time FROM profit_log")
            row = cursor.fetchone()
            if row and row["last_profit_time"]:
                last_profit_time = row["last_profit_time"]
                if last_profit_time.tzinfo is None:
                    last_profit_time = last_profit_time.replace(tzinfo=KST)
                return max(last_profit_time, bid_apply_time)
            else:
                return bid_apply_time
    finally:
        conn.close()


# 수익 계산
def calculate_profit_incremental():
    last_calc_time = get_last_calc_time()
    now = datetime.now(KST)
    print(f"[{now}] ▶ 이전 계산 시점: {last_calc_time}, 현재 시각: {now}")

    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            # 1. 최신 bid_id
            cursor.execute("SELECT MAX(bid_id) AS latest_bid_id FROM bidding_result")
            latest_bid_id = cursor.fetchone()["latest_bid_id"]

            if not latest_bid_id:
                print("⚠️ 최신 bid_id 없음, 계산 종료")
                return

            # 2. 해당 bid_id의 accepted 입찰 정보 + 가격
            cursor.execute("""
                SELECT br.entity_id, bl.bid_price_per_kwh
                FROM bidding_result br
                JOIN bidding_log bl
                  ON br.bid_id = bl.bid_id AND br.entity_id = bl.entity_id
                WHERE br.bid_id = %s AND br.result = 'accepted'
            """, (latest_bid_id,))
            accepted_bids = cursor.fetchall()
            price_map = {row["entity_id"]: row["bid_price_per_kwh"] for row in accepted_bids}

            if not price_map:
                print("⚠️ accepted 입찰 없음, 계산 종료")
                return

            # 3. relay ON 상태만 필터
            cursor.execute("SELECT relay_id FROM relay_status WHERE status = 1")
            on_relays = {row["relay_id"] for row in cursor.fetchall()}

            # 4. 각 entity별 발전 로그 조회 & 수익 계산
            for entity_id, unit_price in price_map.items():
                if entity_id not in on_relays:
                    print(f"⛔ entity_id={entity_id} relay OFF → 계산 생략")
                    continue

                cursor.execute("""
                    SELECT node_timestamp, power_kw
                    FROM node_status_log
                    WHERE relay_id = %s
                    AND node_timestamp > %s AND node_timestamp <= %s
                    ORDER BY node_timestamp ASC
                """, (entity_id, last_calc_time, now))
                logs = cursor.fetchall()

                if not logs:
                    print(f"⚠️ 발전 로그 없음: entity_id={entity_id}")
                    continue

                total_revenue = 0
                for i in range(len(logs)):
                    current_log = logs[i]
                    current_time = current_log["node_timestamp"]
                    if current_time.tzinfo is None:
                        current_time = current_time.replace(tzinfo=KST)

                    power_kw = current_log["power_kw"]

                    if i < len(logs) - 1:
                        next_time = logs[i+1]["node_timestamp"]
                    else:
                        next_time = now
                    if next_time.tzinfo is None:
                        next_time = next_time.replace(tzinfo=KST)

                    time_diff_seconds = (next_time - current_time).total_seconds()
                    revenue = power_kw * unit_price 
                    total_revenue += revenue

                total_revenue = round(total_revenue, 2)
                print(f"✅ entity_id={entity_id} → {len(logs)}개 로그, 수익 {total_revenue}원")

                # DB 저장
                cursor.execute("""
                    INSERT INTO profit_log (timestamp, entity_id, unit_price, revenue_krw)
                    VALUES (%s, %s, %s, %s)
                """, (now, entity_id, unit_price, total_revenue))

            conn.commit()
            print(f"[{now}] 💾 수익 누적 저장 완료")

    except Exception as e:
        print(f"❌ calculate_profit_incremental 오류: {e}")
    finally:
        conn.close()



# 스케줄러
def start_scheduler():
    scheduler = BackgroundScheduler(timezone=KST)

    # 1. 입찰 평가: 매 15분 0초
    scheduler.add_job(evaluate_bids, 'cron', minute='0,15,30,45', second=10, id='evaluate_bids')
    
    # 2. 수익 계산: 매 15분 30초 (relay_status 반영 후)
    scheduler.add_job(calculate_profit_incremental, 'interval', seconds=30, id='calculate_profit_incremental')


    scheduler.start()
    print("📅 APScheduler 시작됨 (15분 간격)")
