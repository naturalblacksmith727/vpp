import requests
import json, re
import time
import sys
from datetime import datetime
from langchain_openai import ChatOpenAI
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

# ✅ 날씨 키 매핑 (영→한)
WEATHER_KEY_MAPPING = {
    "temperature_c": "온도",
    "rainfall_mm": "강수량",
    "humidity_pct": "습도",
    "cloud_cover_okta": "전운량"
}


# def map_weather_keys(weather):
#     return {
#         WEATHER_KEY_MAPPING.get(k, k): v for k, v in weather.items() if k in WEATHER_KEY_MAPPING
#     }

def map_weather_keys(weather: dict) -> dict:
    for k in weather.keys():
        # 키 출력용
        print(f"key before strip: {repr(k)}, after strip: {repr(k.strip())}")
    return {
        WEATHER_KEY_MAPPING.get(k.strip().strip("'").strip('"'), k.strip().strip("'").strip('"')): v
        for k, v in weather.items()
    }

def extract_json_from_text(text: str):
    # 중괄호 쌍으로 된 모든 블록 추출 (비완전)
    json_blocks = re.findall(r'\{.*?\}', text, re.DOTALL)
    if not json_blocks:
        raise ValueError("응답에서 JSON을 찾지 못했습니다.")
    # 가장 긴 블록이 전체 JSON일 가능성이 높음
    json_str = max(json_blocks, key=len)
    return json_str


from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)


# ✅ LLM 프롬프트 구성 및 응답 파싱 함수

import re
import json
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate



def summarize_node_and_weather(node_status, weather, llm):
    import json
    import re

    # 1️⃣ 전달용 JSON 생성
    resource_data = json.dumps({'node': node_status, 'weather': weather}, ensure_ascii=False)

    print("✅ LLM 전달용 JSON:", resource_data)

    # 2️⃣ JSON만 생성하는 프롬프트
    prompt_json = ChatPromptTemplate.from_messages([
    SystemMessage("""
너는 VPP 에너지 입찰 어시스턴트야.

주어진 자원 상태 데이터를 기반으로 아래 기준에 맞춰 JSON 형식의 통합 정보를 생성해줘.
요약문은 **절대 포함하지 마**.

1. 📦 JSON 형식 결과
- 자원: "태양광", "풍력", "배터리"만 포함
- 발전량(generation_kw): 숫자 (소수점 포함)
- 부가정보: 자원별로 영향을 주는 요소만 포함
    - 태양광: 일사량(solar_irradiance), 하늘 상태(cloud_cover_okta 기반으로 '맑음', '흐림' 등 해석)
    - 풍력: 풍속(wind_speed)
    - 배터리: SOC(soc), 충전 상태 등
- status: 발전량 또는 SOC 기준으로 판단 ("정상", "정지", "방전 가능", "충전 중", "주의 필요" 등)

2. 마지막 요소로 날씨 정보를 다음 JSON 형식으로 포함:
"weather": {
    "temperature_c": ...,
    "rainfall_mm": ...,
    "humidity_pct": ...,
    "cloud_cover_okta": ...,
    "solar_irradiance": ...,
    "wind_speed": ...
}

반드시 JSON만 출력해줘. 텍스트나 설명은 포함하지 마.
    """.strip()),
    HumanMessage("자원 상태 데이터:\n\n{resource_data}")
])


    try:
        # Step 1: JSON 응답 받아오기
        res = llm(prompt_json.format_messages())
        print("✅ LLM 응답 원문 ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓")
        print(res.content)
        print("↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑")

        # Step 2: JSON 파싱
        try:
            parsed_json = json.loads(res.content)
        except json.JSONDecodeError:
            json_match = re.search(r'(\{.*\})', res.content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                parsed_json = json.loads(json_str)
            else:
                raise ValueError("응답에서 JSON을 추출하지 못했습니다.")

        print("✅ 추출된 JSON:", parsed_json)

        # Step 3: 요약문 생성 프롬프트
        prompt_summary = ChatPromptTemplate.from_messages([
    SystemMessage("""
너는 VPP 에너지 입찰 어시스턴트야.

주어진 JSON 데이터를 기반으로 한글로 자연스럽고 간결하게 요약해줘.
- 자원 상태와 날씨 조건을 종합적으로 설명
- 자원별 상태, 특이사항, 입찰에 참고할만한 포인트를 언급
- 문장은 간결하되 정보는 풍부하게 제공
- 형식 예시는 아래와 같아:

📄 요약문:
현재 태양광은 일사량 3.1kWh/m², 전운량 0으로 맑은 날씨이며 발전 상태는 정상입니다. 풍력은 풍속 2.8m/s로 발전 가능하며, 배터리는 SOC 68%로 방전 가능합니다. 외부 기온은 32.9°C로 비교적 높은 편입니다.
    """.strip()), HumanMessagePromptTemplate.from_template("데이터:\n\n{json_data}")

])

        # JSON 문자열로 직렬화 (ensure_ascii=False는 한글 깨짐 방지)
        json_text = json.dumps(parsed_json, ensure_ascii=False, indent=2)
        print(json_text)

        messages = prompt_summary.format_messages(json_data=json_text)
        res_summary = llm(messages)
        summary_text = res_summary.content.strip()

        print("📄 요약문:\n", summary_text)

        return parsed_json, summary_text

    except Exception as e:
        print("❌ summarize_node_and_weather 실패:", e)
        raise e



def summarize_smp(smp_data, llm):
    # Step 1: JSON 생성 프롬프트
    prompt_json = [
        {"role": "system", "content": "너는 VPP 시장 입찰 분석 전문가야."},
        {"role": "user", "content": f"""
다음은 최근 SMP 시장 정보야. 아래 예시처럼 JSON 형식으로만 요약해줘. 설명은 하지 말고 JSON만 줘.

예시:
{{
  "avg_SMP_4d": 116.2,
  "today_SMP": 123.0,
  "trend": "상승",
  "comment": "SMP가 지속 상승 중이며, 발전량 증가로 경쟁 심화 예상"
}}

데이터:
{smp_data}
"""}
    ]

    # 1) JSON 생성 요청
    res_json = llm(prompt_json)
    content_json = res_json['choices'][0]['message']['content'].strip()

    # 2) JSON 추출
    try:
        json_match = re.search(r'(\{.*\})', content_json, re.DOTALL)
        if not json_match:
            raise ValueError("JSON 형식을 응답에서 찾지 못했습니다.")
        smp_json = json.loads(json_match.group(1))
    except Exception as e:
        print("❌ SMP JSON 파싱 실패:", e)
        raise

    # Step 2: 요약문 생성 프롬프트
    json_text = json.dumps(smp_json, ensure_ascii=False, indent=2)
    prompt_summary = [
        {"role": "system", "content": "너는 VPP 시장 입찰 분석 전문가야."},
        {"role": "user", "content": f"""
주어진 JSON 데이터를 바탕으로 자연스럽고 간결한 한글 요약문을 작성해줘.
- 최근 평균과 오늘 SMP 비교
- 상승/하락 등 추세 언급
- 경쟁 상황이나 참고 포인트 포함

형식:
📄 요약문:
시장 평균 SMP는 ~원이며, 현재는 ~원으로 (상승/하락)세입니다.
...

데이터:
{json_text}
"""}
    ]

    # 3) 요약문 요청
    res_summary = llm(prompt_summary, smp_json)
    summary_text = res_summary['choices'][0]['message']['content'].strip()

    return smp_json, summary_text



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

# ✅ 안전한 JSON 파싱 함수
def safe_json(response, step_name=""):
    try:
        if response.status_code != 200 or not response.text.strip():
            print(f"⚠️ {step_name} 응답 없음 또는 비정상 상태 코드: {response.status_code}")
            return {"result": "Failed", "reason": "empty_or_error_response"}
        return response.json()
    except json.JSONDecodeError as e:
        print(f"❌ {step_name} JSON 디코딩 오류: {e}")
        print(f"📦 응답 내용 일부: {response.text[:100]}...")
        return {"result": "Failed", "reason": "json_decode_error"}


# ✅ 자동 입찰 파이프라인 실행 함수
def run_bid_pipeline():
    while True:
        now = datetime.now()
        bid_time = now.strftime('%Y-%m-%d %H:%M:00')
        bid_id = now.strftime('%Y%m%d%H%M')
        print(f"\n🚀 실행 시각: {bid_time}")

        try:
            # Step1 응답 원문 출력
            node_status_res = requests.get("http://127.0.0.1:5001/llm_serv/node_status")
            node_status = safe_json(node_status_res, "Step1-node_status")

            if node_status.get("result") != "success":
                raise ValueError("Step1 node_status 실패")

            # 전체 자원 리스트 가져오기
            resources = node_status.get("resources", [])

            if not resources:
                raise ValueError("자원 데이터가 비어있음")

            # 태양광 자원 찾기
            solar_resource = next((r for r in resources if r.get("type") == "태양광"), None)
            if not solar_resource:
                raise ValueError("태양광 자원이 없어서 날씨 추출 불가")


            if not resources:
                raise ValueError("자원 데이터가 비어있음")

            # 날씨 키 필터링 (모든 자원에서 먼저 발견되는 값 사용)
            weather_keys = ["cloud_cover_okta", "humidity_pct", "rainfall_mm", "temperature_c", "solar_irradiance", "wind_speed"]
            weather = {}

            for k in weather_keys:
                matching_keys = [key for key in solar_resource.keys() if key.strip() == k]
                if matching_keys:
                    value = solar_resource[matching_keys[0]]
                    if value == "null":
                        value = None
                    weather[k] = value
                else:
                    print(f"⚠️ 날씨 키 누락됨: {k}")

            print("✅ 통합 추출된 weather dict:", weather)

            # AI 프롬프트에 맞게 노드 상태 중 태양광, 풍력, 배터리만 필터링
            filtered_nodes = []
            for node in resources:
                if node.get("type") in ["태양광", "풍력", "배터리"]:
                    filtered_node = {
                        "type": node.get("type"),
                        "generation_kw": node.get("generation_kw"),
                        "status": node.get("status")
                    }
                    if node.get("type") == "태양광":
                        filtered_node.update({
                            "solar_irradiance": node.get("solar_irradiance"),
                            "cloud_cover_okta": node.get("cloud_cover_okta"),
                        })
                    elif node.get("type") == "풍력":
                        filtered_node.update({
                            "wind_speed": node.get("wind_speed")
                        })
                    elif node.get("type") == "배터리":
                        filtered_node.update({
                            "soc": node.get("soc"),
                        })
                    filtered_nodes.append(filtered_node)

            print("✅ AI 전달용 node list:", filtered_nodes)

            # AI 프롬프트 호출
            res_json, res_summary = summarize_node_and_weather(filtered_nodes, weather, llm)


            # Step 2: SMP 분석
            smp_res = requests.get("http://127.0.0.1:5001/llm_serv/get_smp")
            smp_data_raw = safe_json(smp_res, "Step2-SMP")

            if smp_data_raw.get("result") != "success":
                raise ValueError(f"Step2 실패: {smp_data_raw.get('reason')}")

            smp_data = json.dumps(smp_data_raw["smp_data"], ensure_ascii=False, indent=2)
            smp_summary, smp_text = summarize_smp(smp_data, llm)
            print("📦 Step2 결과:", smp_summary)
            print("📄 Step2 요약:", smp_text)

            # Step 3: 입찰 전략
            bid_result, bid_summary = generate_bid_strategy(res_summary, smp_summary)
            print("📦 Step3 결과:", bid_result)
            print("📄 Step3 요약:", bid_summary)

            # Step 3 결과 → DB 필드명 변환
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

        time.sleep(900)  # 15분 대기

# ✅ 메인 실행
if __name__ == '__main__':
    run_bid_pipeline()