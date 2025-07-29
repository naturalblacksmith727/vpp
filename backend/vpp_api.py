from flask import Flask, request, jsonify
from datetime import datetime, timezone, timedelta
import pymysql
import json
from flask_cors import CORS

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
# 프론트엔드 모든 요청 허용
CORS(app)

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


      
      
      
# 발전소 결과 요청(서버->프론트엔드)
@app.route('/serv_fr/node_status', methods=['GET'])
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
                "solar" : [],
                "wind" : [],
                "battery" : []
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
      
      

 
# 수익 결과 요청(서버->프론트엔드)
@app.route('/serv_fr/bidding_result', methods=['GET'])
def get_profit_rusult():
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
                    "total_revenue_krw" : total_revenue_krw,
                    "total_generation_kwh" : total_generation_kwh
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
    
app.run(debug=True, host='0.0.0.0', port=5000)
