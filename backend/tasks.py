from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pymysql, pytz
from flask import Flask
from flask_cors import CORS


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
            rounded_time_str = rounded_time_kst.strftime('%Y-%m-%d %H:%M')


            cursor.execute("SELECT * FROM bidding_log WHERE bid_id = %s", (latest_bid_id,))
            bids = cursor.fetchall()

            # SMP 가격 조회 시 kst naive datetime 사용
            cursor.execute("SELECT price_krw FROM smp WHERE smp_time = %s", (rounded_time_str,))
            smp_row = cursor.fetchone()
            print(rounded_time_kst)
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
                    """, (rounded_time_str, entity_id))
                    print(f"🟢 relay ON: {entity_id}")
                else:
                    cursor.execute("""
                        UPDATE relay_status SET status = 0, last_updated = %s WHERE relay_id = %s
                    """, (rounded_time_str, entity_id))
                    print(f"🔴 relay OFF: {entity_id}")

            for off_id in off_targets:
                cursor.execute("""
                    UPDATE relay_status SET status = 0, last_updated = %s WHERE relay_id = %s
                """, (rounded_time_str, off_id))
                print(f"⚫ relay FORCE OFF: {off_id} (accepted된 발전소 보호)")

            conn.commit()
            print(f"✅ 입찰 평가 완료: batch {latest_bid_id} (SMP {market_price})")

    except Exception as e:
        conn.rollback()
        print(f"❌ 입찰 평가 오류: {e}")



def calculate_profit_incremental():
    now_kst = datetime.now(KST)
    now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now_str}] ▶ 수익 계산 시작")

    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            # 1. 가장 최신 bid_id
            cursor.execute("SELECT MAX(bid_id) AS latest_bid_id FROM bidding_result")
            latest_bid_id = cursor.fetchone()["latest_bid_id"]
            if not latest_bid_id:
                print("⚠️ 최신 bid_id 없음 → 계산 종료")
                return

            # 2. 해당 bid_id의 accepted 입찰 정보
            cursor.execute("""
                SELECT br.entity_id, bl.bid_price_per_kwh, 
                       DATE_FORMAT(bl.bid_time, '%%Y-%%m-%%d %%H:%%i:%%s') AS bid_time_str
                FROM bidding_result br
                JOIN bidding_log bl
                  ON br.bid_id = bl.bid_id AND br.entity_id = bl.entity_id
                WHERE br.bid_id = %s AND br.result = 'accepted'
            """, (latest_bid_id,))
            accepted_bids = cursor.fetchall()

            # 3. 적용 시간 구간 필터링
            entity_price_map = {}
            for row in accepted_bids:
                bid_time = datetime.strptime(row["bid_time_str"], "%Y-%m-%d %H:%M:%S")
                start_apply = bid_time + timedelta(minutes=15)
                end_apply = bid_time + timedelta(minutes=30)

                if start_apply <= now_kst < end_apply:
                    entity_price_map[row["entity_id"]] = row["bid_price_per_kwh"]

            if not entity_price_map:
                print("⚠️ 현재 적용되는 accepted 입찰 없음 → 계산 종료")
                return

            # 4. ON 상태 릴레이
            cursor.execute("SELECT relay_id FROM relay_status WHERE status = 1")
            on_relays = {row["relay_id"] for row in cursor.fetchall()}

            saved_results = []  # 디버깅용 저장

            # 5. 각 entity별 발전량 계산
            for entity_id, unit_price in entity_price_map.items():
                if entity_id not in on_relays:
                    print(f"⛔ entity_id={entity_id} relay OFF → 생략")
                    continue

                cursor.execute("""
                    SELECT power_kw
                    FROM node_status_log
                    WHERE relay_id = %s
                    AND node_timestamp BETWEEN %s AND %s
                """, (
                    entity_id,
                    (now_kst - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
                    now_str
                ))
                logs = cursor.fetchall()

                if not logs:
                    print(f"⚠️ 발전 로그 없음: entity_id={entity_id}")
                    continue

                total_power_kw = sum(row["power_kw"] for row in logs)
                revenue = round(total_power_kw * unit_price, 2)

                # INSERT
                cursor.execute("""
                    INSERT INTO profit_log (timestamp, entity_id, unit_price, revenue_krw)
                    VALUES (%s, %s, %s, %s)
                """, (now_str, entity_id, unit_price, revenue))

                saved_results.append({
                    "entity_id": entity_id,
                    "power_kw": total_power_kw,
                    "unit_price": unit_price,
                    "revenue": revenue
                })

            conn.commit()

            # 디버깅 출력
            print(f"\n[{now_str}] 💾 수익 저장 완료")
            print("=" * 60)
            for r in saved_results:
                print(f"entity_id={r['entity_id']:<3} | 발전량={r['power_kw']:.4f} kW "
                      f"| 단가={r['unit_price']:.2f} ₩/kWh | 수익={r['revenue']:.2f} ₩")
            print("=" * 60)

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


app = Flask(__name__)
CORS(app)



