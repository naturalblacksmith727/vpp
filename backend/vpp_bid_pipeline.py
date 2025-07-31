import requests
import json
import time
from datetime import datetime
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import SystemMessage, HumanMessage

# ✅ LLM 초기화
llm = ChatOpenAI(model='gpt-4o', temperature=0.3)

# ✅ 키 변환 매핑 (AI 결과 → DB 컬럼명)
KEY_MAPPING = {
    'bid_quantity': 'bid_quantity_kwh',
    'bid_price': 'bid_price_per_kwh',
    'strategy_reason': 'llm_reasoning',
    'recommendation': 'recommendation'
}

# ✅ Step 1 프롬프트 (자원 + 기상 상태 요약)
def summarize_node_and_weather(node_status, weather):
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
너는 VPP 에너지 입찰 어시스턴트야.

1. 📦 JSON 형식 결과
- 자원: "태양광", "풍력", "배터리"만 포함
- 발전량(kW): 숫자 (소수점 포함)
- 부가정보: 자원별로 영향을 주는 요소만 포함
    - 태양광: 일사량, 하늘 상태 (전운량 기반 맑음/흐림 등)
    - 풍력: 풍속
    - 배터리: SOC, 충전 상태
- status: 발전량 또는 SOC 기준으로 판단 ("정상", "정지", "방전 가능", "충전 중", "주의 필요" 등)

2. 마지막 요소로 날씨 정보를 다음 JSON처럼 포함해줘:
{ "온도": ..., "강수량": ..., "습도": ..., "전운량": ... }

3. 📄 요약문: 위 JSON 내용을 한글로 자연스럽게 설명해줘

출력 형식은 반드시 아래처럼 맞춰:
📦 JSON:
[ ... ]
📄 요약문:
            """.strip()
        ),
        (
            "human",
            "자원 상태 데이터:\n\n{resource_data}"
        )
    ])
    resource_data = json.dumps({'node': node_status, 'weather': weather}, ensure_ascii=False)
    res = llm(prompt.format_messages(resource_data=resource_data))
    split = res.content.strip().split("\n", 1)
    return json.loads(split[0]), split[1] if len(split) > 1 else ""

# ✅ Step 2 프롬프트 (SMP 분석)
def summarize_smp(smp_data):
    prompt = ChatPromptTemplate.from_messages([
        ("system", "너는 VPP 시장 입찰 분석 전문가야."),
        ("human", f"""
다음은 최근 SMP 시장 정보야:

{smp_data}

📦 JSON 형식 (시장 분석 정리):
{{
  "avg_SMP_4d": 116.2,
  "today_SMP": 123.0,
  "trend": "상승",
  "comment": "SMP가 지속 상승 중이며, 발전량 증가로 경쟁 심화 예상"
}}

📄 요약문:
시장 평균 SMP는 116.2원이며, 현재는 123원으로 상승세입니다.  
11시대는 발전 여건이 좋아 경쟁이 심화될 것으로 보입니다.
""")
    ])
    res = llm(prompt.format_messages())
    split = res.content.strip().split("\n", 1)
    return json.loads(split[0]), split[1] if len(split) > 1 else ""

# ✅ Step 3 프롬프트 (입찰 전략 생성)
def generate_bid_strategy(resource_json, market_json):
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
{json.dumps(resource_json, ensure_ascii=False)}

📌 시장 분석:
{json.dumps(market_json, ensure_ascii=False)}

출력 예시:
[
  {{
    "resource": "태양광",
    "bid_quantity": 100,
    "bid_price": 120.5,
    "recommendation": "권장",
    "strategy_reason": "..."
  }},
  ...
]
📄 요약문:
...
""")
    ])
    res = llm(prompt.format_messages())
    split = res.content.strip().split("\n", 1)
    return json.loads(split[0]), split[1] if len(split) > 1 else ""

# ✅ 자동 입찰 파이프라인 실행 함수
def run_bid_pipeline():
    while True:
        now = datetime.now()
        bid_time = now.strftime('%Y-%m-%d %H:%M:00')
        bid_id = now.strftime('%Y%m%d%H%M')
        print(f"\n🚀 실행 시각: {bid_time}")

        try:
            # Step 1: 자원 상태 + 날씨
            node_status = requests.get("http://127.0.0.1:5001/llm_serv/node_status").json()
            weather = requests.get("http://127.0.0.1:5001/llm_serv/weather").json()
            res_summary, res_text = summarize_node_and_weather(node_status, weather)
            print("📦 Step1 결과:", res_summary)
            print("📄 Step1 요약:", res_text)

            # Step 2: SMP 분석
            smp_data_raw = requests.get("http://127.0.0.1:5001/llm_serv/get_smp").json()
            smp_data = json.dumps(smp_data_raw, ensure_ascii=False, indent=2)
            smp_summary, smp_text = summarize_smp(smp_data)
            print("📦 Step2 결과:", smp_summary)
            print("📄 Step2 요약:", smp_text)

            # Step 3: 입찰 전략
            bid_result, bid_summary = generate_bid_strategy(res_summary, smp_summary)
            print("📦 Step3 결과:", bid_result)
            print("📄 Step3 요약:", bid_summary)

            # ✅ Step 3 결과 → DB 필드명 변환
            converted_bids = []
            for bid in bid_result:
                converted = {}
                for key, value in bid.items():
                    new_key = KEY_MAPPING.get(key, key)
                    converted[new_key] = value
                converted_bids.append(converted)

            # Step 3-1: DB 전송
            res = requests.post("http://127.0.0.1:5001/llm_serv/generate_bid", json={
                "bid_time": bid_time,
                "bid_id": bid_id,
                "bids": converted_bids
            })

            if res.ok:
                print("✅ 입찰 전략 전송 성공")
            else:
                print(f"❌ 입찰 전송 실패: {res.text}")

        except Exception as e:
            print(f"❌ 오류 발생: {e}")

        # 15분 대기
        time.sleep(900)

# ✅ 메인 실행
if __name__ == '__main__':
    run_bid_pipeline()
