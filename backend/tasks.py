from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pymysql, pytz

def get_connection():
    return pymysql.connect(
        host="database-1.cts2qeeg0ot5.ap-northeast-2.rds.amazonaws.com",
        user="kevin",
        db="vpp_2",
        password="spreatics*",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )

KST = pytz.timezone("Asia/Seoul")

TEST_START = datetime(2025, 8, 7, 13, 30, tzinfo=KST)
TEST_END = datetime(2025, 8, 7, 13, 45, tzinfo=KST)

# datetime.now()가 15분으로 정확히 찍히지 않을 경우 예방하기 위한 15분단위로 반올림 해주는 함수 
def round_to_nearest_15min(dt):
    discard = timedelta(minutes=dt.minute % 15,
                        seconds=dt.second,
                        microseconds=dt.microsecond)
    dt -= discard
    if discard >= timedelta(minutes=7.5):
        dt += timedelta(minutes=15)
    return dt

# 입찰 결과 결정 및 bidding_result와 relay_status에 반영 
def evaluate_bids():
    now = datetime.now(KST)
    print(f"[{now}] ⏳ 입찰 평가 시작")

    try:
        conn = get_connection()
        conn.begin()
        with conn.cursor() as cursor:
            # 최신 bid_id 조회
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

            # 중복 평가 방지
            cursor.execute("SELECT COUNT(*) AS cnt FROM bidding_result WHERE bid_id = %s", (latest_bid_id,))
            if cursor.fetchone()["cnt"] > 0:
                print(f"⚠️ 이미 평가된 입찰 batch {latest_bid_id}, 생략")
                conn.rollback()
                return

            rounded_time = round_to_nearest_15min(now)

            # 입찰 정보
            cursor.execute("SELECT * FROM bidding_log WHERE bid_id = %s", (latest_bid_id,))
            bids = cursor.fetchall()

            # SMP 가격
            cursor.execute("SELECT price_krw FROM smp WHERE smp_time = %s", (rounded_time,))
            smp_row = cursor.fetchone()
            print(rounded_time)
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

                # 평가
                if bid_price is None:
                    result = 'rejected'
                    bid_price_val = None
                else:
                    result = 'accepted' if bid_price <= market_price else 'rejected'
                    bid_price_val = bid_price

                # 결과 저장
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
                    # 조건에 따른 OFF 대상 설정
                    if entity_id == 1:
                        off_targets.add(4)
                    elif entity_id == 2:
                        off_targets.add(5)

            # ✅ 상태 반영: evaluated_entities는 무조건 OFF 또는 ON으로 설정해야 함
            for entity_id in evaluated_entities:
                if entity_id in accepted_entities:
                    cursor.execute("""
                        UPDATE relay_status SET status = 1, last_updated = %s WHERE relay_id = %s
                    """, (rounded_time, entity_id))
                    print(f"🟢 relay ON: {entity_id}")
                else:
                    cursor.execute("""
                        UPDATE relay_status SET status = 0, last_updated = %s WHERE relay_id = %s
                    """, (rounded_time, entity_id))
                    print(f"🔴 relay OFF: {entity_id}")

            # ✅ accepted된 발전소로 인해 OFF 되어야 하는 대상 처리
            for off_id in off_targets:
                cursor.execute("""
                    UPDATE relay_status SET status = 0, last_updated = %s WHERE relay_id = %s
                """, (rounded_time, off_id))
                print(f"⚫ relay FORCE OFF: {off_id} (accepted된 발전소 보호)")

            conn.commit()
            print(f"✅ 입찰 평가 완료: batch {latest_bid_id} (SMP {market_price})")

    except Exception as e:
        conn.rollback()
        print(f"❌ 입찰 평가 오류: {e}")


#수익 계산 - 가장 최근 수익을 계산한 시간 가져오기
def get_last_calc_time():
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT MAX(timestamp) as last_time FROM profit_log")
            row = cursor.fetchone()
            if row and row["last_time"]:
                return row["last_time"]
            else:
                # 처음이면 예를 들어 과거 1시간 전이나 초기값 지정 가능
                from datetime import datetime, timedelta
                return datetime.now(KST) - timedelta(hours=1)
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
            # 1. accepted 입찰 결과 중 최신 bid_id와 entity별 가격 조회
            cursor.execute("""
                SELECT br.entity_id, br.bid_price
                FROM bidding_result br
                JOIN (
                    SELECT entity_id, MAX(id) AS max_id
                    FROM bidding_result
                    WHERE result = 'accepted'
                    GROUP BY entity_id
                ) latest ON br.id = latest.max_id
            """)
            accepted_bids = cursor.fetchall()
            price_map = {bid['entity_id']: bid['bid_price'] for bid in accepted_bids}

            if not price_map:
                print("⚠️ 수익 계산할 accepted 입찰 없음")
                return

            # 2. relay 상태 확인 (ON인 entity만 처리)
            cursor.execute("""
                SELECT relay_id FROM relay_status WHERE status = 1
            """)
            on_relays = set(row['relay_id'] for row in cursor.fetchall())

            # 3. 각 entity별로 last_calc_time ~ now 구간 로그 조회 및 수익 계산
            for entity_id, unit_price in price_map.items():
                if entity_id not in on_relays:
                    print(f"⛔ entity_id={entity_id} relay OFF, 계산 생략")
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
                    current_time = current_log['node_timestamp']
                    power_kw = current_log['power_kw']

                    if i < len(logs) - 1:
                        next_time = logs[i+1]['node_timestamp']
                    else:
                        next_time = now

                    time_diff_seconds = (next_time - current_time).total_seconds()
                    revenue = power_kw * unit_price * (time_diff_seconds / 3600)
                    total_revenue += revenue

                total_revenue = round(total_revenue, 2)
                print(f"✅ entity_id={entity_id} → {len(logs)}개 로그, 수익 {total_revenue}원")

                # profit_log 저장 (현재 시각 기준)
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
