from flask import Flask, request, jsonify, Blueprint
from datetime import datetime, timedelta
import pymysql
import json
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
    try:
        conn = get_connection()

        with conn.cursor() as cursor:
            # 가장 최근 시간 데이터를 가지고 있는 relay_id 1~5번 선택
            sql = """
            SELECT n.*
            FROM node_status_log n
            JOIN(  
                SELECT relay_id, MAX(node_timestamp) AS recent_time
                FROM node_status_log 
                GROUP BY relay_id
                ) l
            ON n.relay_id = l.relay_id AND n.node_timestamp = l.recent_time
            ORDER BY n.relay_id
            """
            cursor.execute(sql)
            rows = cursor.fetchall()

            # 최근 기준 node_status_log 데이터가 없음
            if not rows:
                return jsonify({
                    "status": "failed",
                    "data": None,
                    "timestamp": None,
                    "fail_reason": "no_data_available"
                })

            # 설비별로 데이터 분류
            data = {
                "solar": [],
                "wind": [],
                "battery": []
            }

            for row in rows:
                equip_type = RELAY_TYPE[row["relay_id"]]
                if equip_type:
                    data[equip_type].append({
                        "relay_id": row["relay_id"],
                        "power_kw": row["power_kw"],
                        "soc": row["soc"]
                    })

            return jsonify({
                "status": "success",
                "data": data,
                "timestamp": rows[0]["node_timestamp"].isoformat(),
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
            SELECT ROUND(CAST(SUM(revenue_krw) AS DECIMAL(10,2)), 0) AS total_revenue_krw
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
                    "total_revenue_krw": total_revenue_krw,
                    "total_generation_kwh": total_generation_kwh
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
@vpp_blueprint.route("/serv_fr/generate_bid", methods=["GET"], endpoint="generate_bid_get")
def generate_bid():
    try:
        conn = get_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT entity_id, bid_time, bid_price_per_kwh, bid_quantity_kwh, llm_reasoning
                FROM bidding_log
                ORDER BY bid_time DESC
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
                LIMIT 1
            """
            cursor.execute(sql)
            result = cursor.fetchone()
        conn.close()

        if result is None:
            return jsonify({
                "status": "success",
                "bid": None,
                "fail_reason": "missing_field:bidding_result"
            })

        return jsonify({
            "status": "success",
            "bid": {
                "entity_id": result["entity_id"],
                "bid_result": result["result"],
                "unit_price": result["bid_price"]
            },
            "fail_reason": None
        })

    except Exception:
        return jsonify({
            "status": "success",
            "bid": None,
            "fail_reason": "server_error"
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

        # 오늘 날짜 (base_time 기준)
        today_date = base_time.date()
        base_time_key = today_date.isoformat()

        # 오늘: base_time 이전 3개
        today_offsets = [-45, -30, -15]
        smp_data[base_time_key] = []

        for offset in today_offsets:
            dt = base_time + timedelta(minutes=offset)
            query = "SELECT price_krw FROM smp WHERE smp_time = %s LIMIT 1"
            cursor.execute(query, (dt,))
            result = cursor.fetchone()
            smp_data[base_time_key].append(
                result["price_krw"] if result else None)

        # 전날 ~ 3일 전까지: base_time 기준 - N일
        for i in range(1, 4):
            day_dt = base_time - timedelta(days=i)
            key = day_dt.date().isoformat()
            smp_data[key] = []

            for offset in [-15, 0, 15, 30]:
                dt = day_dt + timedelta(minutes=offset)
                query = "SELECT price_krw FROM smp WHERE smp_time = %s LIMIT 1"
                cursor.execute(query, (dt,))
                result = cursor.fetchone()
                smp_data[key].append(result["price_krw"] if result else None)

        conn.close()

        # 데이터가 모두 None일 경우 no_data 처리
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
    now = datetime.now().replace(second=0, microsecond=0)
    now = datetime.now().replace(second=0, microsecond=0)
    base_time = now

    print(f"[fetch_smp] base_time: {base_time}")

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

        return jsonify({"result": "success", "message": "입찰 전략 저장 완료"}), 200

    except (ValueError, KeyError, TypeError) as e:
        print("❌ 데이터 오류:", str(e))
        return jsonify({"result": "Failed", "reason": "empty_bid_list"}), 400

    except pymysql.err.IntegrityError as e:
        print("❌ IntegrityError:", e)
        return jsonify({"result": "Failed", "reason": f"sql_insert_error: {str(e)}"}), 500

    except pymysql.err.OperationalError as e:
        print("❌ OperationalError:", e)
        return jsonify({"result": "Failed", "reason": "db_connection_error"}), 500

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
            "result": "sucess",
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
@vpp_blueprint.route("/ardu_serv/node_status", methods=["POST"])
def receive_node_status():
    try:
        data = request.get_json()

        required_fields = ["relay_id", "node_timestamp", "power_kw", "soc"]
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "result": "failed",
                    "node_timestamp": data.get("node_timestamp"),
                    "reason": f"Missing required field: {field}"
                })

        try:
            datetime.strptime(data["node_timestamp"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return jsonify({
                "result": "failed",
                "node_timestamp": data["node_timestamp"],
                "reason": "Invalid timestamp format"
            })

        if not isinstance(data["power_kw"], (float, int)):
            return jsonify({
                "result": "failed",
                "node_timestamp": data["node_timestamp"],
                "reason": "Invalid type: power_kw must be float"
            })

        if data["soc"] is not None and not isinstance(data["soc"], (float, int)):
            return jsonify({
                "result": "failed",
                "node_timestamp": data["node_timestamp"],
                "reason": "Invalid type: soc must be float or null"
            })

        node_status_storage.append(data)

        # DB 저장
        conn = get_connection()
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO node_status_log (node_timestamp, relay_id, power_kw, soc)
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(sql, (
                data["node_timestamp"],
                data["relay_id"],
                data["power_kw"],
                data["soc"]
            ))
        conn.commit()
        conn.close()

        return jsonify({
            "result": "Success",
            "node_timestamp": data["node_timestamp"],
            "reason": None
        })

    except Exception as e:
        return jsonify({
            "result": "failed",
            "node_timestamp": None,
            "reason": "Unexpected server error"
        })


# 2. GET/command: 입찰 결과 반영 relay 상태값 전소 (serv->ardu)
@vpp_blueprint.route("/serv_ardu/command", methods=["GET"])
def get_all_commands():
    try:
        page = int(request.args.get("page", 1))
        page_size = 20  # 한 번에 20개씩 전송
        offset = (page - 1) * page_size

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
            LIMIT {page_size} OFFSET {offset}
            """
            cursor.execute(sql)
            results = cursor.fetchall()
        conn.close()

        commands = []
        for row in results:
            commands.append({
                "relay_id": row["relay_id"],
                "status": row["status"],
                "last_updated": row["last_updated"].strftime("%Y-%m-%d %H:%M:%S"),
                "reason": row.get("reason")  # NULL인 경우도 처리
            })

        return jsonify({
            "status": "success",
            "commands": commands,
            "fail_reason": None
        })

    except Exception as e:
        return jsonify({
            "status": "failed",
            "commands": None,
            "fail_reason": f"internal server error: {str(e)}"
        })
