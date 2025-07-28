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
def test_db_connection():
    try:
        conn = get_connection()
        print("DB connection success")
        conn.close()
    except Exception as e:
        print("DB connection failed:", e)

app = Flask(__name__)
# 프론트엔드 모든 요청 허용
CORS(app)

# relay_id 발전소 타입
RELAY_TYPE = {
    1:"solar",
    2:"wind",
    3:"battery",
    4:"solar",
    5:"wind"
}
# --------------------------------------------------------------------------------
# 프론트 <-> 서버
# --------------------------------------------------------------------------------
# 1. node_status: 발전소 결과 요청(서버->프론트엔드)
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



# 2. profit: 수익 결과 요청(서버->프론트엔드)
@app.route('/serv_fr/profit', methods=['GET'])
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
    

# --------------------------------------------------------------------------------
# LLM <-> 서버
# --------------------------------------------------------------------------------

# 1. get_smp: SMP 데이터 요청 (LLM -> 서버)
# 15분마다 smp 데이터 가져오기

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
    1:"solar",
    2:"wind",
    3:"battery",
    4:"solar",
    5:"wind"
}
# --------------------------------------------------------------------------------
# 프론트 <-> 서버
# --------------------------------------------------------------------------------
# 1. node_status: 발전소 결과 요청(서버->프론트엔드)
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



# 2. profit: 수익 결과 요청(서버->프론트엔드)
@app.route('/serv_fr/profit', methods=['GET'])
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
    

# --------------------------------------------------------------------------------
# LLM <-> 서버
# --------------------------------------------------------------------------------

# 1. get_smp: SMP 데이터 요청 (LLM -> 서버)
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
            smp_data[base_time_key].append(result["price_krw"] if result else None)

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

@app.route("/llm_serv/get_smp", methods=["GET"])
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
# 2. get_weather: 날씨 데이터 요청 (LLM -> 서버)
# 15분마다 날씨 데이터 정리해서 가져오기 
@app.route("/llm_serv/get_weather", methods= ["GET"])
def get_weather():
    pass






# --------------------------------------------------------------------------------
# 아두이노 <-> 서버
# --------------------------------------------------------------------------------

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


      
     















if __name__ == "__main__":
    # DB 연결 테스트 (필요하면 여기서 실행)
    test_db_connection()
    # Flask 앱 실행
    app.run(debug=True, host='0.0.0.0', port=5001)