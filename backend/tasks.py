from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pymysql

def get_connection():
    return pymysql.connect(
        host="database-1.cts2qeeg0ot5.ap-northeast-2.rds.amazonaws.com",
        user="kevin",
        db="vpp_2",
        password="spreatics*",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )

# datetime.now()가 15분으로 정확히 찍히지 않을 경우 예방하기 위한 15분단위로 반올림 해주는 함수 
def round_to_nearest_15min(dt):
    discard = timedelta(minutes=dt.minute % 15,
                        seconds=dt.second,
                        microseconds=dt.microsecond)
    dt -= discard
    if discard >= timedelta(minutes=7.5):
        dt += timedelta(minutes=15)
    return dt


def evaluate_bids():
    print(f"[{datetime.now()}] ⏳ 입찰 평가 시작")
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            # 최신 입찰 배치 ID 조회
            cursor.execute("SELECT MAX(bid_id) AS latest_bid_id FROM bidding_log")
            row = cursor.fetchone()
            latest_bid_id = row["latest_bid_id"]

            if not latest_bid_id:
                print("🚫 평가할 입찰 없음")
                return

            # 이미 평가된 적 있는지 확인
            cursor.execute("""
                SELECT COUNT(*) AS cnt FROM bidding_result WHERE bid_id = %s
            """, (latest_bid_id,))
            if cursor.fetchone()["cnt"] > 0:
                print(f"⚠️ 이미 평가된 입찰 batch {latest_bid_id}, 생략")
                return
            
            rounded_time = round_to_nearest_15min(datetime.now())

            # 해당 배치의 입찰 정보 가져오기
            cursor.execute("""
                SELECT * FROM bidding_log WHERE bid_id = %s
            """, (latest_bid_id,))
            bids = cursor.fetchall()

            # 현재 SMP 단가 조회 (가장 가까운 값 사용)
            cursor.execute("""
                SELECT price_per_kwh
                FROM smp_data
                WHERE smp_time = %s
                ORDER BY timestamp DESC
                LIMIT 1
            """, (rounded_time,))
            smp_row = cursor.fetchone()
            if not smp_row:
                print("❌ SMP 데이터 없음")
                return

            market_price = smp_row["price_per_kwh"]

            # 평가 및 결과 저장
            for bid in bids:
                result = 'accepted' if bid["bid_price_per_kwh"] <= market_price else 'rejected'

                cursor.execute("""
                    INSERT INTO bidding_result (bid_id, entity_id, quantity_kwh, bid_price, result)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    latest_bid_id,
                    bid["entity_id"],
                    bid["bid_quantity_kwh"],
                    bid["bid_price_per_kwh"],
                    result
                ))

            conn.commit()
            print(f"✅ 입찰 평가 완료: batch {latest_bid_id} (SMP {market_price})")

    except Exception as e:
        print("❌ 에러 발생:", str(e))
    finally:
        conn.close()




#profit_log 계산 








# 스케줄러 설정
def start_scheduler():
    scheduler = BackgroundScheduler(timezone='Asia/Seoul')
    scheduler.add_job(evaluate_bids, 'cron', minute='*/15')  # 매 15분마다 실행
    scheduler.start()
    print("📅 APScheduler 시작됨 (15분 간격)")


# 메인 진입점
if __name__ == "__main__":
    start_scheduler()
    # 앱이 종료되지 않도록 유지
    try:
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        print("🛑 종료됨")
