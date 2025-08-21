import traceback  # 파일 상단에 추가
from flask import Flask, request, jsonify, Blueprint
from datetime import datetime, timedelta
import pytz
import pymysql
import json
from flask_cors import CORS
from enum import Enum


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


vpp_blueprint = Blueprint("vpp", __name__)


@vpp_blueprint.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "running"})


# --------------------------------------------------------------------------------
# 사용하는 ID, Key, 유틸 등
# --------------------------------------------------------------------------------
# 키 변환 매핑 (generate_bid용)
KEY_MAPPING = {
    'bid_quantity': 'bid_quantity_kwh',
    'bid_price': 'bid_price_per_kwh',
    'strategy_reason': 'llm_reasoning'
}

# relay_id 매핑용
RELAY_MAPPING = {
    1: '태양광', 4: '태양광',
    2: '풍력',  5: '풍력',
    3: '배터리'
}

# 자원 유형별 기상필드 매핑
RESOURCE_EXTRA_FIELDS = {
    '태양광': ['solar_irradiance'],
    '풍력': ['wind_speed'],
    '배터리': ['soc']
}

# relay_id 발전소 타입
RELAY_TYPE = {
    1: "solar",
    2: "wind",
    3: "battery",
    4: "solar",
    5: "wind"
}
ENTITY_TYPE = {
    1: "태양광",
    2: "풍력",
    3: "배터리"
}

#  PUT/fr_serv/bid_edit_fix 에서 사용할 enum 클래스

class StatusEnum(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class ActionEnum(str, Enum):
    EDIT = "edit"
    CONFIRM = "confirm"
    TIMEOUT = "timeout"

KST = pytz.timezone("Asia/Seoul")

# 타임 아웃 체크 함수(한국시간 기준 15분마다 14분  지났는지 확인)
def is_timeout():
    now = datetime.now(KST)
    minute = (now.minute // 15) * 15
    start_time = now.replace(minute=minute, second=0, microsecond=0)
    timeout_time = start_time + timedelta(minutes=14)

    return now > timeout_time
    

# 가장 가까운 15분 단위로 반올림
def round_to_nearest_15min(dt: datetime = None):
    if dt is None:
        dt = datetime.now(KST)
    discard = timedelta(minutes=dt.minute % 15,
                        seconds=dt.second,
                        microseconds=dt.microsecond)
    dt -= discard
    if discard >= timedelta(minutes=7.5):
        dt += timedelta(minutes=15)
    return dt.replace(second=0, microsecond=0)


# 메모리 저장소
node_status_storage = []


# 유틸 함수 (실제로는 DB 또는 하드웨어에서 확인해야 함)
def is_relay_connected(relay_id):
    return True


def is_entity_active(relay_id):
    return True


# --------------------------------------------------------------------------------
# 프론트 <-> 서버
# --------------------------------------------------------------------------------

# 1. GET/node_status: 발전소 node_status: 발전소 결과 요청(서버->프론트엔드)
@vpp_blueprint.route('/serv_fr/node_status', methods=['GET'])
def get_node_result():
    # 설비별로 데이터 분류
    data = {
        "solar": [],
        "wind": [],
        "battery": []
    }

    try:
        conn = get_connection()

        with conn.cursor() as cursor:
            # 태양광 시간별 전력량
            sql = """
            SELECT node_timestamp AS timestamp, ROUND(sum(power_kw),2) AS power_kw, round(avg(soc),4) AS soc
            FROM node_status_log
            WHERE relay_id IN (1, 4)
                AND node_timestamp >= (SELECT MAX(node_timestamp) FROM node_status_log) - INTERVAL 24 HOUR  
            GROUP BY node_timestamp
            ORDER BY node_timestamp;
            """
            cursor.execute(sql)
            rows = cursor.fetchall()

            
            data["solar"] = [{"timestamp": row["timestamp"].strftime(
                '%Y-%m-%d %H:%M:%S'), "power_kw": row["power_kw"], "soc":row["soc"]} for row in rows]

            # 풍력 시간별 전력량
            sql = """
            SELECT node_timestamp AS timestamp, ROUND(sum(power_kw),2) AS power_kw, round(avg(soc),4) AS soc
            FROM node_status_log
            WHERE relay_id IN (2, 5)
                AND node_timestamp >= (SELECT MAX(node_timestamp) FROM node_status_log) - INTERVAL 24 HOUR  
            GROUP BY node_timestamp
            ORDER BY node_timestamp;
            """
            cursor.execute(sql)
            rows = cursor.fetchall()

            
            data["wind"] = [{"timestamp": row["timestamp"].strftime(
                '%Y-%m-%d %H:%M:%S'), "power_kw": row["power_kw"], "soc":row["soc"]} for row in rows]

            # 배터리 시간별 순충전전력량 (relay_id 4,5는 더하고 3은 뺌)
            sql = """
            SELECT charging.timestamp AS timestamp, ROUND(charging.power_kw - COALESCE(usaged.power_kw,0),2) AS power_kw
            FROM
                (
                    SELECT node_timestamp AS timestamp, ROUND(sum(power_kw),2) AS power_kw
                    FROM node_status_log
                    WHERE relay_id IN (4,5)
                        AND node_timestamp >= (SELECT MAX(node_timestamp) FROM node_status_log) - INTERVAL 24 HOUR
                    GROUP BY node_timestamp
                ) AS charging
            LEFT JOIN
                (
                    SELECT node_timestamp AS timestamp, power_kw
                    FROM node_status_log
                    WHERE relay_id IN (3)
                        AND node_timestamp >= (SELECT MAX(node_timestamp) FROM node_status_log) - INTERVAL 24 HOUR
                ) AS usaged
            ON charging.timestamp = usaged.timestamp
            ORDER BY charging.timestamp;
            """
            cursor.execute(sql)
            rows = cursor.fetchall()

            soc_sql = """
            """

            
            data["battery"] = [{"timestamp": row["timestamp"].strftime(
                '%Y-%m-%d %H:%M:%S'), "power_kw": row["power_kw"]} for row in rows]

            return jsonify({
                "status": "success" if any([data["solar"],data["wind"], data["battery"]]) else "failed",
                "data": data,
                "timestamp": datetime.now().isoformat(timespec='seconds'),
                "fail_reason": None if any([data["solar"],data["wind"], data["battery"]]) else "no_data_avilable"
            })

    # 서버 내부 문제
    except Exception as e:
        print("에러 발생: ", str(e))
        return jsonify({
            "status": "failed",
            "data": None,
            "timestamp": None,
            "fail_reason": "server_error"
        })


# 2. GET/profit: 지금까지 얻은 총 수익 보여주기 (프론트 -> 서버)
@vpp_blueprint.route('/serv_fr/profit', methods=['GET'])
def get_profit_result():
    try:
        conn = get_connection()

        with conn.cursor() as cursor:
            sql = """
            SELECT round(sum(power_kw*(20.0/3600)),2) AS total_generation_kwh
            FROM node_status_log 
            WHERE relay_id IN (1,2,4,5)
            """
            cursor.execute(sql)
            total_generation_kwh = cursor.fetchone()

            sql = """
            SELECT ROUND((SUM(revenue_krw)), 1) AS total_revenue_krw
            FROM profit_log
            """
            cursor.execute(sql)
            total_revenue_krw = cursor.fetchone()

            if total_generation_kwh is None:
                # 데이터가 아예 없을 때 실패 처리
                return jsonify({
                    "status": "failed",
                    "data": None,
                    "timestamp": None,
                    "fail_reason": "no_data_total_generation_kwh"
                })

            if total_revenue_krw is None:
                # 데이터가 아예 없을 때 실패 처리
                return jsonify({
                    "status": "failed",
                    "data": None,
                    "timestamp": None,
                    "fail_reason": "no_data_total_revenue_krw"
                })

            return jsonify({
                "status": "success",
                "data": {
                    "total_revenue_krw": total_revenue_krw["total_revenue_krw"],
                    "total_generation_kwh": total_generation_kwh["total_generation_kwh"]
                },
                "fail_reason": None
            })

    # 서버 내부 문제
    except Exception as e:
        print("에러 발생: ", str(e))
        return jsonify({
            "status": "failed",
            "data": None,
            "timestamp": None,
            "fail_reason": "server_error"
        })


# 3. GET/generate_bid: 생성한 입찰 보여주기 (서버 -> 프론트)
@vpp_blueprint.route("/serv_fr/generate_bid", methods=["GET"])
def get_generate_bid():
    try:
        conn = get_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT *
                FROM bidding_log
                ORDER BY bid_time DESC
                LIMIT 3
            """
            cursor.execute(sql)
            bids = cursor.fetchall()
        conn.close()

        if not bids:
            return jsonify({
                "fail_reason": "No LLM output: Failed to generate bidding strategy",
                "bids": None
            })

        result = []
        for bid in bids:
            result.append({
                "bid_id":bid["bid_id"],
                "entity_id": bid["entity_id"],
                "bid_time": bid["bid_time"].strftime("%Y-%m-%d %H:%M:%S"),
                "bid_price_per_kwh": bid["bid_price_per_kwh"],
                "bid_quantity_kwh": bid["bid_quantity_kwh"],
                "llm_reasoning": bid["llm_reasoning"]
            })

        return jsonify({
            "fail_reason": None,
            "bids": result
        })

    except Exception:
        return jsonify({
            "fail_reason": "server_error",
            "bids": None
        })


# 4. GET/bidding_result: 입찰 결과 내용 보여주기 (서버 -> 프론트)
@vpp_blueprint.route("/serv_fr/bidding_result", methods=["GET"])
def get_bidding_result():
    try:
        conn = get_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT entity_id, result, bid_price
                FROM bidding_result
                WHERE bid_id = (
            SELECT MAX(bid_id) FROM bidding_result
        )
            """
            cursor.execute(sql)
            results = cursor.fetchall()
        conn.close()

        if results is None:
            return jsonify({
                "status": "success",
                "bid": None,
                "fail_reason": "missing_field:bidding_result"
            })
        
        return jsonify({
            "status": "success",
            "bid": results,
            "fail_reason": None
        })

    except Exception:
        return jsonify({
            "status": "success",
            "bid": None,
            "fail_reason": "server_error"
        })

# 5. PUT/bid_edit_fix: 사용자 응답 처리 및 최종 입찰 확정(프론트엔드->서버)
@vpp_blueprint.route('/fr_serv/bid_edit_fix', methods=['PUT'])
def put_edit_fix():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "").strip().lower()
    bids = data.get("bids", None)

    # ---------------------
    # [1] 타임아웃 처리
    # ---------------------
    if action == "timeout":
        try:
            conn = get_connection()
            with conn.cursor() as cursor:
                # 가장 최근의 bid_time에 해당하는 bid_id 찾기
                cursor.execute("""
                    SELECT MAX(bid_time) AS latest_time
                    FROM bidding_log
                """)
                latest_time_row = cursor.fetchone()
                latest_time = latest_time_row["latest_time"]

                if not latest_time:
                    return jsonify({
                        "status": StatusEnum.FAILED,
                        "action": ActionEnum.TIMEOUT,
                        "fail_reason": "Timeout failed: No bid data found"
                    })

                # 최신 시간에 해당하는 bid_id 목록 가져오기
                cursor.execute("""
                    SELECT bid_id, entity_id
                    FROM bidding_log
                    WHERE bid_time = %s
                """, (latest_time,))
                bid_rows = cursor.fetchall()

                if not bid_rows:
                    return jsonify({
                        "status": StatusEnum.FAILED,
                        "action": ActionEnum.TIMEOUT,
                        "fail_reason": "Timeout failed: No bids to update"
                    })

                # 각 입찰 항목의 가격을 0으로 업데이트
                for row in bid_rows:
                    cursor.execute("""
                        UPDATE bidding_log
                        SET bid_price_per_kwh = 0
                        WHERE bid_id = %s AND entity_id = %s
                    """, (row["bid_id"], row["entity_id"]))

                conn.commit()

                return jsonify({
                    "status": StatusEnum.SUCCESS,
                    "action": ActionEnum.TIMEOUT,
                    "fail_reason": None
                })
        except Exception as e:
            return jsonify({
                "status": StatusEnum.FAILED,
                "action": ActionEnum.TIMEOUT,
                "fail_reason": "Timeout processing failed: DB error"
            })

    # ---------------------
    # [2] confirm (수정 없이 진행)
    # ---------------------
    elif action == "confirm":
        try:
            conn = get_connection()
            with conn.cursor() as cursor:

                # 마지막 입찰 데이터 확인
                cursor.execute("""
                    SELECT COUNT(*) AS count
                    FROM bidding_log
                    WHERE entity_id IN (1,2,3)
                """)
                result = cursor.fetchone()
                if result["count"] == 0:
                    return jsonify({
                        "status": StatusEnum.FAILED,
                        "action": action,
                        "fail_reason": "Cannot confirm: No existing bid data found"
                    })

                return jsonify({
                    "status": StatusEnum.SUCCESS,
                    "action": action,
                    "fail_reason": None
                })
        except Exception:
            return jsonify({
                "status": StatusEnum.FAILED,
                "action": action,
                "fail_reason": "Confirmation failed: Unable to update bidding record"
            })

    # ---------------------
    # [3] edit (DB 수정)
    # ---------------------
    elif action == "edit":
        # 데이터 누락
        if not bids or not isinstance(bids, list):
            return jsonify({
                "status": "failed",
                "action": action,
                "fail_reason": "Missing bid data: Price or entity not provided"
            })

        ENTITY_NAME_TO_ID = {"태양광": 1, "풍력": 2, "배터리": 3}

        try:
            conn = get_connection()

            with conn.cursor() as cursor:
                for bid in bids:
                    bid_id = bid["bid_id"]
                    entity_name = bid["entity_name"]
                    new_price = bid["bid_price_per_kwh"]

                    target_entity_id = ENTITY_NAME_TO_ID.get(entity_name)

                    # 허용되지 않은 entity
                    if target_entity_id is None:
                        return jsonify({
                            "status": "failed",
                            "action": action,
                            "fail_reason": "Invalid entity: Must be one of ['태양광', '풍력', '배터리']"
                        })

                    sql = """
                    SELECT *
                    FROM bidding_log
                    WHERE bid_id = %s and entity_id = %s
                    """
                    cursor.execute(sql,(bid_id, target_entity_id))

                    row = cursor.fetchone()

                    if row:
                        sql = """
                        UPDATE bidding_log
                        SET bid_price_per_kwh = %s
                        WHERE bid_id = %s AND entity_id = %s
                        """
                        cursor.execute(sql,(new_price, row["bid_id"], target_entity_id))

                conn.commit()

                # edit, confirm, timeout
                return jsonify({
                    "status": StatusEnum.SUCCESS,
                    "action": action,
                    "fail_reason": None
                })

        except Exception as e:
            return jsonify({
                "status": StatusEnum.FAILED,
                "action": action,
                "fail_reason": "Failed to save user edit: Database error"
            })
    else:
        return jsonify({
            "status": StatusEnum.FAILED,
            "action": action,
            "fail_reason": "Internal server error while processing user response"
        })
# --------------------------------------------------------------------------------
# LLM <-> 서버
# --------------------------------------------------------------------------------

# 1. GET/get_smp: SMP 데이터 요청 (LLM -> 서버)
# 15분마다 smp 데이터 가져오기
def fetch_smp_for_time_blocks(base_time):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        smp_data = {}

        today_date = base_time.date()
        base_time_key = today_date.isoformat()

        today_offsets = [-45, -30, -15]
        smp_data[base_time_key] = []

        for offset in today_offsets:
            dt = base_time + timedelta(minutes=offset)
            
            # ✅ KST → UTC 변환 후 문자열 포맷
            dt_utc = dt.astimezone(UTC)
            dt_str = dt_utc.strftime("%Y-%m-%d %H:%M:%S")

            query = "SELECT price_krw FROM smp WHERE smp_time = %s LIMIT 1"
            cursor.execute(query, (dt_str,))
            result = cursor.fetchone()
            smp_data[base_time_key].append(
                result["price_krw"] if result else None
            )

        # 전날 ~ 3일 전
        for i in range(1, 4):
            day_dt = base_time - timedelta(days=i)
            key = day_dt.date().isoformat()
            smp_data[key] = []

            for offset in [-15, 0, 15, 30]:
                dt = day_dt + timedelta(minutes=offset)
                
                # ✅ 동일하게 UTC 변환
                dt_utc = dt.astimezone(UTC)
                dt_str = dt_utc.strftime("%Y-%m-%d %H:%M:%S")

                query = "SELECT price_krw FROM smp WHERE smp_time = %s LIMIT 1"
                cursor.execute(query, (dt_str,))
                result = cursor.fetchone()
                smp_data[key].append(
                    result["price_krw"] if result else None
                )

        conn.close()

        if all(all(v is None for v in values) for values in smp_data.values()):
            return {"error": "no_data"}

        return smp_data

    except pymysql.MySQLError as e:
        print("MySQL error:", e)
        return {"error": "no_db_connection"}
    except Exception as e:
        print("Unexpected error:", e)
        return {"error": "invalid_format"}


@vpp_blueprint.route("/llm_serv/get_smp", methods=["GET"])
def get_smp():
    # 🔄 15분 단위로 정렬된 시각 사용
    base_time = round_to_nearest_15min()

    print(f"[fetch_smp] base_time (rounded): {base_time}")

    smp_result = fetch_smp_for_time_blocks(base_time)

    if isinstance(smp_result, dict) and "error" in smp_result:
        reason = smp_result["error"]
        message_map = {
            "no_data": "SMP data unavailable for requested period",
            "no_db_connection": "Internal server error during SMP data fetch",
            "invalid_format": "Invalid SMP format in database"
        }
        return jsonify({
            "result": "failed",
            "reason": reason,
            "message": message_map.get(reason, "Unknown error")
        }), 500

    return jsonify({
        "result": "success",
        "timestamp": base_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "smp_data": smp_result
    })


# 2. GET/get_weather: 날씨 데이터 요청 (LLM -> 서버)
# 15분마다 날씨 데이터 정리해서 가져오기
@vpp_blueprint.route("/llm_serv/get_weather", methods=["GET"])
def get_weather():
    pass


# 3. Post/generate_bid: 생성한 입찰 제안 bidding_log에 저장 (LLM -> 서버)
@vpp_blueprint.route('/llm_serv/generate_bid', methods=['POST'], endpoint="generate_bid_post")
def generate_bid():
    try:
        data = request.get_json()
        bid_time = data.get('bid_time')
        # bid_id = data.get('bid_id')
        bids = data.get('bids')

        if not isinstance(bid_time, str) or not isinstance(bids, list):
            raise ValueError("invalid request format")

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT MAX(bid_id) FROM bidding_log")
        last_bid_id_row = cursor.fetchone()
        last_bid_id = last_bid_id_row.get('MAX(bid_id)') or 0  # 수정됨
        new_bid_id = last_bid_id + 1

        for bid in bids:
            for old_key, new_key in KEY_MAPPING.items():
                if old_key in bid:
                    bid[new_key] = bid.pop(old_key)

            required_fields = ['entity_id', 'recommendation',
                               'llm_reasoning', 'bid_quantity_kwh']
            for field in required_fields:
                if field not in bid:
                    raise ValueError(f"missing field: {field}")

            entity_id = bid['entity_id']
            recommendation = bid['recommendation']
            llm_reasoning = bid['llm_reasoning']

            if recommendation == "입찰 비권장":
                bid_quantity_kwh = 0.0
                bid_price_per_kwh = None
            else:
                if 'bid_price_per_kwh' not in bid:
                    raise ValueError("missing bid_price_per_kwh")
                bid_quantity_kwh = bid.get('bid_quantity_kwh', 0.0) or 0.0
                bid_price_per_kwh = bid.get('bid_price_per_kwh', 0.0) or 0.0

            cursor.execute("""
                INSERT INTO bidding_log 
                (bid_time, bid_id, entity_id, bid_quantity_kwh, bid_price_per_kwh, llm_reasoning, recommendation)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                bid_time, new_bid_id, entity_id,
                bid_quantity_kwh, bid_price_per_kwh,
                llm_reasoning, recommendation
            ))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"result": "success", "message": "입찰 전략 저장 완료"}), 100

    except (ValueError, KeyError, TypeError) as e:
        print("❌ 데이터 오류:", str(e))
        return jsonify({"result": "Failed", "reason": "empty_bid_list"}), 200

    except pymysql.err.IntegrityError as e:
        print("❌ IntegrityError:", e)
        return jsonify({"result": "Failed", "reason": f"sql_insert_error: {str(e)}"}), 300

    except pymysql.err.OperationalError as e:
        print("❌ OperationalError:", e)
        return jsonify({"result": "Failed", "reason": "db_connection_error"}), 400

    except Exception as e:
        print("❌ Unknown Error:", e)
        return jsonify({"result": "Failed", "reason": "internal_server_error"}), 500


# 4. GET /llm_serv/node_status: 입찰 생성 위해 발전소, 날씨 상태 가져오기 (LLM -> serv)
@vpp_blueprint.route('/llm_serv/node_status', methods=['GET'])
def get_node_status():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        latest_logs = {}
        for relay_id, res_type in RELAY_MAPPING.items():
            cursor.execute("""
                SELECT 
                    ns.*, 
                    (
                        SELECT w.solar_irradiance
                        FROM weather w
                        WHERE w.obs_time <= DATE_FORMAT(ns.node_timestamp, '%%Y-%%m-%%d %%H:00:00')
                        ORDER BY w.obs_time DESC
                        LIMIT 1
                    ) AS solar_irradiance,
                    (
                        SELECT w.wind_speed
                        FROM weather w
                        WHERE w.obs_time <= DATE_FORMAT(ns.node_timestamp, '%%Y-%%m-%%d %%H:00:00')
                        ORDER BY w.obs_time DESC
                        LIMIT 1
                    ) AS wind_speed,
                    (
                        SELECT w.rainfall_mm
                        FROM weather w
                        WHERE w.obs_time <= DATE_FORMAT(ns.node_timestamp, '%%Y-%%m-%%d %%H:00:00')
                        ORDER BY w.obs_time DESC
                        LIMIT 1
                    ) AS rainfall_mm,
                    (
                        SELECT w.cloud_cover_okta
                        FROM weather w
                        WHERE w.obs_time <= DATE_FORMAT(ns.node_timestamp, '%%Y-%%m-%%d %%H:00:00')
                        ORDER BY w.obs_time DESC
                        LIMIT 1
                    ) AS cloud_cover_okta,
                    (
                        SELECT w.humidity_pct
                        FROM weather w
                        WHERE w.obs_time <= DATE_FORMAT(ns.node_timestamp, '%%Y-%%m-%%d %%H:00:00')
                        ORDER BY w.obs_time DESC
                        LIMIT 1
                    ) AS humidity_pct,
                    (
                        SELECT w.temperature_c
                        FROM weather w
                        WHERE w.obs_time <= DATE_FORMAT(ns.node_timestamp, '%%Y-%%m-%%d %%H:00:00')
                        ORDER BY w.obs_time DESC
                        LIMIT 1
                    ) AS temperature_c
                FROM node_status_log ns
                WHERE ns.relay_id = %s
                ORDER BY ns.node_timestamp DESC
                LIMIT 1
            """, (relay_id,))
            result = cursor.fetchone()
            if result:
                if res_type not in latest_logs or result['node_timestamp'] > latest_logs[res_type]['node_timestamp']:
                    latest_logs[res_type] = result

        if not latest_logs:
            return jsonify({"result": "Failed", "reason": "no_data"}), 200

        resources = []
        missing_fields = []
        timestamps = [entry['node_timestamp']
                      for entry in latest_logs.values()]
        timestamp = max(timestamps).strftime("%Y-%m-%dT%H:%M:%S")

        for res_type, log in latest_logs.items():
            resource_data = {
                "type": res_type,
                "generation_kw": log.get("power_kw"),
                "status": log.get("status") or "정상",
                "rainfall_mm": log.get("rainfall_mm"),
                "cloud_cover_okta": log.get("cloud_cover_okta"),
                "humidity_pct": log.get("humidity_pct"),
                "temperature_c": log.get("temperature_c")
            }

            for field in RESOURCE_EXTRA_FIELDS.get(res_type, []):
                if field in log and log[field] is not None:
                    resource_data[field] = log[field]
                else:
                    missing_fields.append(field)

            resources.append(resource_data)

        cursor.close()
        conn.close()

        if missing_fields:
            return jsonify({
                "result": "Failed",
                "partial_missing": {
                    "missing_fields": list(set(missing_fields))
                }
            }), 200

        return jsonify({
            "result": "success",
            "timestamp": timestamp,
            "resources": resources
        }), 200

    except pymysql.err.OperationalError as e:
        print(f"❌ DB 연결 오류: {e}")
        return jsonify({"result": "Failed", "reason": "db_connection_error"}), 500

    except Exception as e:
        print(f"❌ 내부 오류: {e}")
        return jsonify({"result": "Failed", "reason": "internal_server_error"}), 500


# --------------------------------------------------------------------------------
# 아두이노 <-> 서버
# --------------------------------------------------------------------------------

# 1. POST/node_status: 아두이노 상태 전송 (ardu -> serv)

# 1. POST/node_status: 아두이노 상태 전송 (ardu -> serv)

@vpp_blueprint.route("/ardu_serv/node_status", methods=["POST"])
def receive_node_status():
    try:
        data = request.get_json()

        required_fields = ["relay_id", "power_kw", "soc"]
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "result": "failed",
                    "node_timestamp": None,
                    "reason": f"Missing required field: {field}"
                })

        if not isinstance(data["power_kw"], (float, int)):
            return jsonify({
                "result": "failed",
                "node_timestamp": None,
                "reason": "Invalid type: power_kw must be float"
            })

        if data["soc"] is not None and not isinstance(data["soc"], (float, int)):
            return jsonify({
                "result": "failed",
                "node_timestamp": None,
                "reason": "Invalid type: soc must be float or null"
            })

        node_status_storage.append(data)

        # DB 저장 (node_timestamp는 DB에서 자동 생성됨)
        conn = get_connection()
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO node_status_log (relay_id, power_kw, soc)
            VALUES (%s, %s, %s)
            """
            cursor.execute(sql, (
                data["relay_id"],
                data["power_kw"],
                data["soc"]
            ))

            # 새로 삽입된 레코드의 timestamp 조회
            cursor.execute(
                "SELECT node_timestamp FROM node_status_log WHERE id = LAST_INSERT_ID()"
            )
            result = cursor.fetchone()

            if result:
                # DictCursor인 경우와 튜플 커서인 경우 둘 다 대응
                node_timestamp = result["node_timestamp"] if isinstance(
                    result, dict) else result[0]
            else:
                node_timestamp = None

        conn.commit()
        conn.close()

        return jsonify({
            "result": "Success",
            "node_timestamp": node_timestamp.strftime("%Y-%m-%d %H:%M:%S") if node_timestamp else None,
            "reason": None
        })

    except Exception as e:
        print("Error in /ardu_serv/node_status:", e)
        traceback.print_exc()
        return jsonify({
            "result": "failed",
            "node_timestamp": None,
            "reason": f"Unexpected server error: {str(e)}"
        })


# 2. GET/command: 입찰 결과 반영 relay 상태값 전소 (serv->ardu)
@vpp_blueprint.route("/serv_ardu/command", methods=["GET"])
def get_all_commands():
    try:

        conn = get_connection()
        with conn.cursor() as cursor:
            sql = """
            SELECT 
                rs.relay_id,
                rs.status,
                rs.last_updated,
                br.result AS reason
            FROM relay_status rs
            LEFT JOIN (
                SELECT bid_id, result
                FROM bidding_result
                WHERE id IN (
                    SELECT MAX(id)
                    FROM bidding_result
                    GROUP BY bid_id
                )
            ) br ON rs.relay_id = br.bid_id
            """
            cursor.execute(sql)
            results = cursor.fetchall()
        conn.close()

        commands = []
        for row in results:
            commands.append({
                "relay_id": row["relay_id"],
                "status": row["status"]
            })

        return jsonify({
            "result": "success",
            "commands": commands,
            "fail_reason": None
        })

    except Exception as e:
        return jsonify({
            "result": "failed",
            "commands": None,
            "fail_reason": f"internal server error: {str(e)}"
        })
