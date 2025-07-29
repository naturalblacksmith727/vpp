from flask import Flask, request, jsonify
import pymysql
from datetime import datetime

app = Flask(__name__)

# ✅ DB 연결 함수 (공통)
def get_db_connection():
    return pymysql.connect(
        host='database-1.cts2qeeg0ot5.ap-northeast-2.rds.amazonaws.com',
        user='kevin',
        password='spreatics*',
        db='vpp_2',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# ✅ 키 변환 매핑 (generate_bid용)
KEY_MAPPING = {
    'bid_quantity': 'bid_quantity_kwh',
    'bid_price': 'bid_price_per_kwh',
    'strategy_reason': 'llm_reasoning'
}

# ✅ relay_id → 자원 유형 매핑
RELAY_MAPPING = {
    1: '태양광', 4: '태양광',
    2: '풍력',  5: '풍력',
    3: '배터리'
}

# ✅ 자원 유형별 기상필드 매핑
RESOURCE_EXTRA_FIELDS = {
    '태양광': ['solar_irradiance'],
    '풍력': ['wind_speed'],
    '배터리': ['soc']
}

# ✅ POST /llm_serv/generate_bid
@app.route('/llm_serv/generate_bid', methods=['POST'])
def generate_bid():
    try:
        data = request.get_json()
        bid_time = data.get('bid_time')
        bid_id = data.get('bid_id')
        bids = data.get('bids')

        if not isinstance(bid_time, str) or not isinstance(bid_id, int) or not isinstance(bids, list):
            raise ValueError("invalid request format")

        conn = get_db_connection()
        cursor = conn.cursor()

        for bid in bids:
            for old_key, new_key in KEY_MAPPING.items():
                if old_key in bid:
                    bid[new_key] = bid.pop(old_key)

            required_fields = ['entity_id', 'recommendation', 'llm_reasoning', 'bid_quantity_kwh']
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
                bid_time, bid_id, entity_id,
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

# ✅ GET /llm_serv/node_status
@app.route('/llm_serv/node_status', methods=['GET'])
def get_node_status():
    try:
        conn = get_db_connection()
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
        timestamps = [entry['node_timestamp'] for entry in latest_logs.values()]
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

# ✅ Flask 앱 실행
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
