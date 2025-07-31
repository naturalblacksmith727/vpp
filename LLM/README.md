# AI prompt

## Step1. 자원별 실시간 상태요약

- 코드
    
    ```python
    import json
    import requests
    from langchain.prompts import ChatPromptTemplate
    from langchain.chat_models import ChatOpenAI
    from langchain.chains import LLMChain
    
    # ✅ OpenAI 설정
    openai_api_key = "sk-..."  # 🔐 본인의 OpenAI API 키로 교체
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2, openai_api_key=openai_api_key)
    
    # ✅ 자원 상태를 API에서 불러오기
    def fetch_resource_data_from_api():
        try:
            url = "http://your-server-address/api/node_status/latest"  
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
    
            # 간결한 리스트 컴프리헨션 방식으로 프롬프트 입력 변환
            return "\n".join(
                f"{item['name']}, {item['power_kw']}, {item['info']}, {item['status']}"
                for item in data
            )
    
        except Exception as e:
            print("❌ API 호출 실패:", e)
            return None  # 실패 시 None 반환
    
    # ✅ 프롬프트 템플릿 정의
    prompt = ChatPromptTemplate.from_messages([
        ("system", "너는 VPP 에너지 입찰 어시스턴트야.\n아래 자원 상태 데이터를 바탕으로 JSON 형식 결과와 요약문을 만들어줘.\nJSON은 다음 키를 포함해야 해: 자원, 발전량(kW), 부가정보, status"),
        ("human", "자원 상태 데이터:\n\n{resource_data}")
    ])
    
    # ✅ LangChain 체인 생성
    status_chain = LLMChain(llm=llm, prompt=prompt)
    
    # ✅ API 호출 → LangChain 입력값 구성
    resource_data = fetch_resource_data_from_api()
    
    if resource_data is None:
        print("❌ 자원 상태 데이터를 불러오지 못해 종료합니다.")
        exit(1)
    
    resource_input = {
        "resource_data": resource_data
    }
    
    # ✅ 체인 실행
    response = status_chain.invoke(resource_input)
    gpt_output = response["text"]
    
    # ✅ 결과 파싱 및 출력
    try:
        json_part = gpt_output.split("📄")[0].replace("📦 JSON:", "").strip()
        summary_part = gpt_output.split("📄 요약문:")[1].strip()
    
        print("📦 JSON 결과")
        parsed_json = json.loads(json_part)
        print(json.dumps(parsed_json, indent=2, ensure_ascii=False))
    
        print("\n📄 요약문")
        print(summary_part)
    
    except Exception as e:
        print("[❌ 파싱 오류 발생]")
        print(str(e))
        print("GPT 원본 출력:\n", gpt_output)
    \
    ```
    
- 출력예시
    
    ```json
    📦 JSON:
    [
      {
        "자원": "태양광",
        "발전량(kW)": 0.42,
        "부가정보": "일사량 710W/m² (맑음)",
        "status": "정상"
      },
      {
        "자원": "풍력",
        "발전량(kW)": 0.36,
        "부가정보": "풍속 3.8m/s (약간 감소)",
        "status": "정상"
      },
      {
        "자원": "배터리",
        "발전량(kW)": 0.18,
        "부가정보": "SOC 75%, 충전 중",
        "status": "방전 가능"
      },
      {
      "온도": 25.3,
      "강수량": 0.0,
      "습도": 60,
      "전운량": 2,
      }
    ]
    ```
    
    ### 📄 요약문 (프론트 표시용)
    
    ```json
    📄 요약문:
    모든 자원은 정상 상태이며 발전량도 안정적입니다.  
    태양광은 일사량이 좋고, 풍력은 약간 감소했지만 여전히 유효한 상태입니다.  
    배터리는 SOC가 높아 방전 가능 상태입니다.
    ```
    
- 최종 수정코드
    
    ```json
    import json
    import time
    import requests
    from langchain.prompts import ChatPromptTemplate
    from langchain.chat_models import ChatOpenAI
    from langchain.chains import LLMChain
    
    # ✅ OpenAI 설정
    openai_api_key = "sk-..."  
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2, openai_api_key=openai_api_key)
    
    # ✅ relay_id → 자원 이름 매핑
    RELAY_NAME_MAPPING = {
        1: "태양광",
        2: "풍력",
        3: "배터리"
    }
    
    # ✅ 자원 상태 + 날씨 정보를 API에서 불러와 간결한 입력 문자열로 구성
    def fetch_resource_data_from_api():
        try:
            url = "http://your-server-address/api/node_status/latest" 
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
    
            resource_lines = []
    
            for item in data:
                if 'relay_id' not in item:
                    # ✅ 날씨 정보 구성 (weather 컬럼 기준)
                    weather_line = (
                        f"온도: {item['temperature_c']}, "
                        f"강수량: {item['rainfall_mm']}, "
                        f"습도: {item['humidity_pct']}%, "
                        f"전운량: {item['cloud_cover_okta']}"
                    )
                    resource_lines.append(weather_line)
                    continue
    
                name = RELAY_NAME_MAPPING.get(item["relay_id"], f"자원{item['relay_id']}")
                line = f"{name}, 발전량: {item['power_kw']}kW"
    
                # ✅ 자원별 필요한 부가정보만 추가
                if name == "태양광":
                    line += f", 일사량: {item['solar_irradiance']}W/m², 전운량: {item['cloud_cover_okta']}"
                elif name == "풍력":
                    line += f", 풍속: {item['wind_speed']}m/s"
                elif name == "배터리":
                    line += f", SOC: {item.get('soc')}"
    
                resource_lines.append(line)
    
            return "\n".join(resource_lines)
    
        except Exception as e:
            print("❌ API 호출 실패:", e)
            return None
    
    # ✅ 프롬프트 정의 (자원별 부가정보 기준 명시)
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
    너는 VPP 에너지 입찰 어시스턴트야.
    
    아래 자원 상태 데이터를 바탕으로 다음을 생성해줘:
    
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
    ...
            """.strip()
        ),
        (
            "human",
            "자원 상태 데이터:\n\n{resource_data}"
        )
    ])
    
    # ✅ LangChain 체인 생성
    status_chain = LLMChain(llm=llm, prompt=prompt)
    
    # ✅ 실행 루프: 15분마다 자동 실행
    if __name__ == "__main__":
        while True:
            print("\n🚀 [실행] LangChain 입찰 분석 시작...")
            resource_data = fetch_resource_data_from_api()
    
            if resource_data is None:
                print("❌ 자원 상태 데이터를 불러오지 못해 다음 실행까지 대기합니다.")
            else:
                response = status_chain.invoke({"resource_data": resource_data})
                gpt_output = response["text"]
    
                # ✅ 결과 파싱
                try:
                    json_part = gpt_output.split("📄")[0].replace("📦 JSON:", "").strip()
                    summary_part = gpt_output.split("📄 요약문:")[1].strip()
    
                    print("📦 JSON 결과")
                    print(json.dumps(json.loads(json_part), indent=2, ensure_ascii=False))
                    print("\n📄 요약문")
                    print(summary_part)
    
                except Exception as e:
                    print("[❌ 파싱 오류 발생]")
                    print(str(e))
                    print("GPT 원본 출력:\n", gpt_output)
    
            # ✅ 15분 대기
            print("\n⏳ 15분 후 재실행...\n")
            time.sleep(900)
    
    ```
    

## Step2. 시장 환경 분석

- 코드
    
    ```python
    from langchain.prompts import ChatPromptTemplate
    from langchain.chat_models import ChatOpenAI
    from langchain.chains import LLMChain
    import json
    
    # ✅ OpenAI 설정
    openai_api_key = "sk-..."  # 본인의 키 입력
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2, openai_api_key=openai_api_key)
    
    # ✅ Step 2 프롬프트: 시장 환경 분석
    prompt = ChatPromptTemplate.from_messages([
        ("system", "너는 VPP 시장 입찰 분석 전문가야."),
        ("human", """
    다음은 최근 SMP 시장 정보야:
    
    - 2025-07-13: 111.8원
    - 2025-07-14: 112.9원
    - 2025-07-15: 117.1원
    - 2025-07-16: 123.0원 (입찰 예정일)
    
    또한, 현재 시간대(11:15~11:30)는 발전량 증가가 예상되는 구간이야.
    
    📦 JSON 형식 (시장 분석 정리):
    {
      "avg_SMP_4d": 116.2,
      "today_SMP": 123.0,
      "trend": "상승",
      "comment": "SMP가 지속 상승 중이며, 발전량 증가로 경쟁 심화 예상"
    }
    
    📄 요약문:
    시장 평균 SMP는 116.2원이며, 현재는 123원으로 상승세입니다.  
    11시대는 발전 여건이 좋아 경쟁이 심화될 것으로 보입니다.
    """)
    ])
    
    # ✅ LangChain 체인
    market_chain = LLMChain(llm=llm, prompt=prompt)
    
    # ✅ 실행
    response = market_chain.invoke({})
    gpt_output = response["text"]
    
    # ✅ 결과 분리 및 출력
    try:
        json_part = gpt_output.split("📄")[0].replace("📦 JSON 형식 (시장 분석 정리):", "").strip()
        summary_part = gpt_output.split("📄 요약문:")[1].strip()
    
        print("📦 JSON 결과")
        parsed_json = json.loads(json_part)
        print(json.dumps(parsed_json, indent=2, ensure_ascii=False))
    
        print("\n📄 요약문")
        print(summary_part)
    
    except Exception as e:
        print("[❌ 파싱 오류 발생]")
        print(str(e))
        print("GPT 원본 출력:\n", gpt_output)
    
    ```
    
- 출력예시
    
    ### 📄 JSON (프론트 표시용)
    
    ```json
    {
      "avg_SMP_4d": 116.2,
      "today_SMP": 123.0,
      "trend": "상승",
      "comment": "SMP가 지속 상승 중이며, 발전량 증가로 경쟁 심화 예상"
    }
    ```
    
    ### 📄 요약문 (프론트 표시용)
    
    ```
    최근 4일간 SMP 평균은 116.2원이며, 입찰일 SMP는 123.0원으로 상승세입니다.
    현재 시점은 SMP가 지속적인 가격 상승 흐름이 나타나고 있어, 경쟁 수준은 높음입니다.
    ```
    

## Step3. 추천입찰전략

- 코드
    
    ```json
    # ✅ Step 3: 입찰 전략 추천 (JSON + 요약문 분리)
    bid_prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="너는 VPP 입찰 전략 전문가야."),
        HumanMessage(content="""
    아래 자원 상태와 시장 분석을 바탕으로, 자원별 입찰 전략을 수립해줘.  
    각 자원에 대해 다음 정보를 아래 순서대로 JSON으로 출력하고, 요약문도 함께 작성해줘.
    
    - apply_time: 입찰 적용 시간 (ex. "11:15~11:30")
    - bid_amount_kw: 입찰 전력량 (비권장일 경우 0.0)
    - bid_price: 입찰가 (비권장일 경우 null)
    - recommendation: 입찰 권장 / 입찰 비권장
    - strategy_reason: 판단 이유 요약
    
    📌 자원 상태 요약:
    - 태양광: 0.38kW, 일사량 690W/m² (맑음), 상태: 정상
    - 풍력: 0.35kW, 풍속 4.0m/s (점진적 증가), 상태: 정상
    - 배터리: 0.15kW, SOC 10%, 상태: 충전 중 (방전 불가)
    
    📌 시장 분석 요약:
    - 평균 SMP (4일): 116.2원
    - 오늘 SMP: 123.0원 (상승세)
    - 현재 시간: 11:15~11:30, 발전량 증가 예상
    
    📦 JSON 결과:
    { 각 자원별 입찰 전략 }
    
    📄 요약문:
    { 사용자에게 보여줄 설명 요약 }
    """)
    ])
    bid_chain = bid_prompt | llm
    
    # 실행
    bid_result = bid_chain.invoke({})
    full_text = bid_result.content
    
    # ✅ JSON 파트와 요약문 분리
    json_part = full_text.split("📄 요약문:")[0].split("📦 JSON 결과:")[1].strip()
    summary_part = full_text.split("📄 요약문:")[1].strip()
    
    # ✅ 출력
    print("\n📦 입찰 전략 JSON:")
    print(json_part)
    
    print("\n📄 요약문 (프론트 표시용):")
    print(summary_part)
    
    ```
    
- 출력예시
    
    ### 📄 JSON (프론트 표시용)
    
    ```json
    📦 JSON 결과:
    {
      "태양광": {
        "apply_time": "11:15~11:30",
        "bid_amount_kw": 0.38,
        "bid_price": 124,
        "recommendation": "입찰 권장",
        "strategy_reason": "일사량이 높고 SMP가 상승세이므로 수익성 확보 가능"
      },
      "풍력": {
        "apply_time": "11:15~11:30",
        "bid_amount_kw": 0.35,
        "bid_price": 123,
        "recommendation": "입찰 권장",
        "strategy_reason": "풍속이 안정적이며 현재 SMP 수준에서 수익 기대"
      },
      "배터리": {
        "apply_time": "11:15~11:30",
        "bid_amount_kw": 0.0,
        "bid_price": null,
        "recommendation": "입찰 비권장",
        "strategy_reason": "SOC가 낮아 방전 불가"
      }
    }
    ```
    
    ### 📄 요약문 (프론트 표시용)
    
    ```diff
    
    📄 요약문:
    태양광과 풍력은 현재 환경에서 입찰이 권장됩니다.  
    특히 SMP가 상승세이고 일사량 및 풍속 조건이 안정적이어서 기대 수익이 높습니다.  
    반면, 배터리는 SOC 부족으로 인해 방전이 어려워 입찰이 비권장됩니다.
    
    ```
    

