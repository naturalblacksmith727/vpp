from flask import Flask, request, jsonify
from datetime import datetime
import pymysql
from flask_cors import CORS

# DB 연결 함수


def get_connection():
    return pymysql.connect(
        host="database-1.cts2qeeg0ot5.ap-northeast-2.rds.amazonaws.com",
        user="kevin",
        db="vpp_2",
        password="spreatics*",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )


app = Flask(__name__)
CORS(app)

# 메모리 저장소
node_status_storage = []


# 유틸 함수 (실제로는 DB 또는 하드웨어에서 확인해야 함)
def is_relay_connected(relay_id):
    return True


def is_entity_active(relay_id):
    return True


# 1. 아두이노 → 서버: 상태 전송
@app.route("/ardu_serv/node_status", methods=["POST"])
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


# 2. 서버 → 아두이노: 명령 전송
@app.route("/serv_ardu/command", methods=["GET"])
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


# 3. 서버 -> 프론트 : LLM이 생성한 입찰 결과를 프론트로 전달
@app.route("/serv_fr/generate_bid", methods=["GET"])
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


# 4. 서버 -> 프론트 : 입찰 결과 확인
@app.route("/serv_fr/bidding_result", methods=["GET"])
def get_bidding_result():
    try:
        conn = get_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT entity_id, result, bid_price
                FROM bidding_result
                ORDER BY bid_time DESC
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


# Flask 앱 실행
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
