from flask import Flask, request, jsonify
import pymysql
from datetime import datetime
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import SystemMessage, HumanMessage
import requests
import os
import time
import threading
import json

app = Flask(__name__)

# ✅ DB 연결 함수
def get_db_connection():
    return pymysql.connect(
        host='database-1.cts2qeeg0ot5.ap-northeast-2.rds.amazonaws.com',
        user='kevin',
        password='spreatics*',
        db='vpp_2',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# ✅ 키 변환 매핑 (AI 결과 → DB 컬럼명)
KEY_MAPPING = {
    'bid_quantity': 'bid_quantity_kwh',
    'bid_price': 'bid_price_per_kwh',
    'strategy_reason': 'llm_reasoning',
    'recommendation': 'recommendation'
}

# ✅ AI 모델 초기화
llm = ChatOpenAI(model='gpt-4o', temperature=0.3)

# ✅ Step 1: 자원 상태 요약
@app.route('/llm_serv/node_status', methods=['GET'])
def node_status_summary():
    node_status_res = requests.get("http://127.0.0.1:5001/llm_serv/node_status").json()
    weather_res = requests.get("http://127.0.0.1:5001/llm_serv/weather").json()

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="너는 VPP 시스템의 자원 분석 전문가야."),
        HumanMessage(content=f"""
📌 자원 상태:
{node_status_res}

📌 최신 기상 정보:
{weather_res}

위 정보를 바탕으로 각 자원의 상태를 간결하게 요약해줘.
JSON으로 자원별 상태 요약을 주고, 아래에는 요약 설명문도 추가해줘.
""")
    ])

    response = llm(prompt.format_messages())
    split_res = response.content.split("\n", 1)
    summary_json = split_res[0]
    summary_text = split_res[1] if len(split_res) > 1 else ""

    return jsonify({
        "result": "success",
        "summary_json": summary_json,
        "summary_text": summary_text
    })

# ✅ Step 2: SMP 시장 분석
@app.route('/llm/get_smp', methods=['GET'])
def get_smp_summary():
    smp_res = requests.get("http://127.0.0.1:5001/llm_serv/get_smp").json()

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="너는 전력 시장의 SMP 분석 전문가야."),
        HumanMessage(content=f"""
📌 최근 4일간 SMP 데이터:
{smp_res}

이 데이터를 기반으로 현재 SMP 가격 추세를 분석하고 시장 상황을 요약해줘.
JSON과 요약문 형태로 알려줘.
""")
    ])

    response = llm(prompt.format_messages())
    split_res = response.content.split("\n", 1)
    smp_json = split_res[0]
    smp_text = split_res[1] if len(split_res) > 1 else ""

    return jsonify({
        "result": "success",
        "smp_json": smp_json,
        "smp_text": smp_text
    })

# ✅ Step 3: 입찰 전략 생성 및 DB 저장
@app.route('/llm_serv/generate_bid', methods=['POST'])
def generate_bid():
    try:
        data = request.get_json()
        bid_time = data['bid_time']
        bid_id = data['bid_id']
        bids = data['bids']

        conn = get_db_connection()
        cursor = conn.cursor()

        for bid in bids:
            entity_type = bid['resource']
            entity_mapping = {'태양광': 1, '풍력': 2, '배터리': 3}
            entity_id = entity_mapping.get(entity_type)

            insert_data = {
                'bid_time': bid_time,
                'bid_id': bid_id,
                'entity_id': entity_id
            }

            for k, v in KEY_MAPPING.items():
                val = bid.get(k)
                if k == 'recommendation' and val == '비권장':
                    insert_data['bid_quantity_kwh'] = None
                    insert_data['bid_price_per_kwh'] = None
                elif k in ['bid_quantity', 'bid_price', 'strategy_reason']:
                    insert_data[v] = val

            sql = '''
                INSERT INTO bidding_log (bid_time, bid_id, entity_id, bid_quantity_kwh, bid_price_per_kwh, llm_reasoning)
                VALUES (%s, %s, %s, %s, %s, %s)
            '''
            cursor.execute(sql, (
                insert_data['bid_time'], insert_data['bid_id'], insert_data['entity_id'],
                insert_data['bid_quantity_kwh'], insert_data['bid_price_per_kwh'], insert_data['llm_reasoning']
            ))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"result": "success", "message": "입찰 전략 저장 완료"})

    except Exception as e:
        return jsonify({"result": "error", "message": str(e)})

# ✅ 서버 준비까지 대기
def wait_for_server():
    while True:
        try:
            r = requests.get("http://127.0.0.1:5001/llm_serv/node_status")
            if r.status_code == 200:
                print("✅ 서버 준비 완료")
                break
        except:
            print("⏳ 서버 준비 대기 중...")
            time.sleep(2)

# ✅ 자동 실행: 15분마다 Step1~3 수행
def run_bid_pipeline():
    wait_for_server()

    while True:
        now = datetime.now()
        bid_time = now.strftime('%Y-%m-%d %H:%M:00')
        bid_id = now.strftime('%Y%m%d%H%M')

        try:
            # Step 1
            node_status = requests.get("http://127.0.0.1:5001/llm_serv/node_status").json()
            response_text1 = node_status.get("summary_json", "").strip()
            resource_json = json.loads(response_text1)

            # Step 2
            smp = requests.get("http://127.0.0.1:5001/llm/get_smp").json()
            response_text2 = smp.get("smp_json", "").strip()
            market_json = json.loads(response_text2)

            # Step 3 Prompt
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content="너는 VPP 입찰 전략 전문가야."),
                HumanMessage(content=f"""
아래 자원 상태와 시장 분석을 바탕으로, 자원별 입찰 전략을 수립해줘.  
각 자원에 대해 다음 정보를 아래 순서대로 JSON으로 출력하고, 요약문도 함께 작성해줘.

- resource: 자원명 (태양광, 풍력, 배터리)
- bid_quantity: 입찰 전력량 (kWh)
- bid_price: 입찰 가격 (원/kWh)
- recommendation: 권장/비권장
- strategy_reason: 판단 근거 요약문

📌 자원 상태 요약:
{resource_json}

📌 시장 분석:
{market_json}
""")
            ])

            response = llm(prompt.format_messages())
            bid_json_text = response.content.strip().split("\n")[0]
            bids = json.loads(bid_json_text)

            requests.post("http://127.0.0.1:5001/llm_serv/generate_bid", json={
                "bid_time": bid_time,
                "bid_id": bid_id,
                "bids": bids
            })

            print(f"✅ 자동 입찰 실행 완료: {bid_time}")

        except json.JSONDecodeError as e:
            print(f"❌ JSON 파싱 실패: {e}")
            print(f"응답 내용:\n{response.content}")
        except Exception as e:
            print(f"❌ 파이프라인 오류: {e}")

        time.sleep(900)  # 15분 간격

# ✅ Flask 실행 및 파이프라인 병렬 실행
if __name__ == '__main__':
    threading.Thread(target=run_bid_pipeline, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
