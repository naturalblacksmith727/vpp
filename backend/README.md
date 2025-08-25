# 백엔드 구조
'''
[서버 시작]
    │
    ▼
app.py 실행 → Flask 서버 시작
         └── vpp_api.py의 모든 API 등록
         └── tasks.py의 주기적 작업 등록 및 실행
    │
    ▼
vpp_bid_pipeline.py 실행 → 15분 마다 OpenAI API 연동

    │
    ▼   
[Postman에서 API 호출]
    └→ vpp_api.py 내부 라우터 실행

[자동 작업]
    └→ 15분마다: evaluate_bids() → 입찰 평가 → bidding_result에 저장
    └→ 20초마다: calculate_profit() → 실시간 수익 계산 → profit_log에 저장
'''

# REST API spec

## 프론트↔서버 ↔ LLM

![rest api 구조.png](vpp/readme 자료/rest_api_구조.png)

# 데이터베이스

![image.png](vpp/readme 자료/image 3.png)

### 요소 테이블

### 0-1. `entity` – 발전소, 배터리, 아두이노 엔티티를 정리한 표

| 칼럼명 | 타입 | 설명 |
| --- | --- | --- |
| entity_id | INT (PK) | 각 엔티티(설비)의 고유 식별 번호 |
| entity_type | ENUM | 엔티티 종류 (solar, wind, battery, grid) |
| entity_name | VARCHAR | 엔티티의 이름 또는 별칭 (예: 태양광, 아두이노) |

EX)

| entity_id | entity_type | entity_name |
| --- | --- | --- |
| 1 | solar | 태양광 |
| 2 | wind | 풍력 |
| 3 | battery | 배터리 |
| 4 | load  | 아두이노(부하) |

### 0-2. `relay` – 릴레이를 정의한 표

| 칼럼명 | 타입 | 설명 |
| --- | --- | --- |
| relay_id | INT (PK) | 각 릴레이의 고유 식별 번호 |
| source_entity_id | INT (FK) | 릴레이에 연결된 시작 entity_id. enity 테이블의 entity_id 참조. |
| target_entity_id | INT | 릴레이에 연결된 끝 entity_id. enity 테이블의 entity_id 참조. |
| description | VARCHAR | 릴레이 설명  |

EX)

| **relay_id** | **source_entity_id** | **target_entity_id** | **description** |
| --- | --- | --- | --- |
| 1 | 1 | 4 | 태양- 부하 |
| 2 | 2 | 4 | 풍력 - 부하 |
| 3 | 3 | 4 | 배터리- 부하 |
| 4 | 1 | 3 | 태양 - 배터리 |
| 5 | 2 | 3 | 풍력 - 배터리  |

아두이노 실제 설계

| **relay_id** | **source_entity_id** | **target_entity_id** | **description** |
| --- | --- | --- | --- |
| 1 | 1 | 4 | 태양- 부하 |
| 2 | 2 | 4 | 풍력 - 부하 |
| 3 | 1 | 3 | 태양 - 배터리 |
| 4 | 2 | 3 | 풍력 - 배터리  |
| 5 | 3 | 4 | 배터리- 부하 |

### 1. `node_status_log` – 발전소 및 배터리 상태 실시간 기록 [HW → 아두이노 → SQL]

| 컬럼명 | 타입 | 설명 |
| --- | --- | --- |
| id | INT (PK, AI) | 고유 ID |
| timestamp | DATETIME | 측정 시간 (1분 단위) |
| relay_id | INT (FK) | 전력을 보내는 entity, entity 테이블의 entity_id를 참조 (1,2,3 만 올 수 있음) |
| power_kw | FLOAT  | 순간 전력(발전 또는 소비)량 [kW]. source에서 target으로 흐르는 전력의 크기 |
| soc | FLOAT (NULLABLE) | state of charge(충전 상태, %). 배터리 관련 데이터에만 기록되며, 그 외에는 NULL
[source_id or target_id가 3일때] |

Ex)

| **id** | **timestamp** | **relay_id** | **power_kw** | **soc** |
| --- | --- | --- | --- | --- |
| 1 | 2025-07-05 13:15 | 1 | 0.45 | NULL |
| 2 | 2025-07-05 13:15 | 3 | 0.20 | 68.2 |
| 3 | 2025-07-05 13:16 | 1 | 0.10 | 68.3 |

### 2. relay_status 릴레이 현 시점의 상태를 기록 [HW ↔ 아두이노 ↔ SQL ↔ 알고리즘]

| **칼럼명** | **타입** | **설명** |
| --- | --- | --- |
| relay_id | INT | 릴레이 식별자, Primary Key |
| status | TINYINT(1) | 1=ON, 0=OFF (현재 상태) |
| last_updated | DATETIME | 마지막 변경 시각 |

EX)

| **relay_id** | **status** | **last_updated** |
| --- | --- | --- |
| 1 | 1 | 2025-07-17 13:15:00 |
| 2 | 0 | 2025-07-17 13:15:00 |
| 3 | 1 | 2025-07-17 13:15:00 |
| 4 | 0 | 2025-07-17 13:15:00 |
| 5 | 1 | 2025-07-17 13:15:00 |

### 입찰 테이블

### 3. `bidding_log` – LLM이 생성한 입찰 제안 정보 기록 [LLM → SQL] 입찰 생길 때마다 3 row씩 증가

| **컬럼명** | **타입** | **설명** |
| --- | --- | --- |
| id | INT (PK, AI) | 입찰 고유 번호 |
| timestamp | DATETIME | 입찰 시각 (시장 시간과 동일) |
| entity_id | text (FK) | 발전소 id (enity.entity_id 참조) |
| bid_quantity_kwh | FLOAT | 거래 제안량 (kWh) |
| bid_price_per_kwh | FLOAT | 제안 단가 (원/kWh 등) |
| llm_reasoning | TEXT | LLM의 전략 요약 (입찰 근거 및 전략 설명) |

EX)

| **id** | **timestamp** | entity_id | **bid_quantity_kwh** | **bid_price_per_kwh** | **llm_reasoning** |
| --- | --- | --- | --- | --- | --- |
| 1 | 2025-07-15 13:00 | 1 | 100 | 120 | 태양광 발전량 예측치가 높아 입찰 |
| 2 | 2025-07-15 13:00 | 2 | 50 | 130 | 배터리 SOC 충분, 시장가 상승 예측 |
| 3 | 2025-07-15 13:00 | 3 | 80 | 125 | 풍력 발전량 증가 예상 |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |

### 3. `bidding_result` – 입찰 수락/거절 + 행동 기록 [알고리즘 → API → 아두이노]

| **칼럼명** | **타입** | **설명** |
| --- | --- | --- |
| id | INT | 기본키, 자동 증가 |
| bid_id | INT(FK) | 해당 입찰 건 (bidding_log.id 참조) |
| entity_id | INT | 자원(태양광, 풍력 등) 식별자 |
| quantity_kwh | FLOAT | 해당 자원의 입찰 전력량 (kWh) |
| bid_price | FLOAT | 해당 자원의 입찰가 (원/kWh) |
| result | ENUM | 'accepted' 또는 'rejected' (입찰 결과) |

EX) 입찰 결과 나올 때마다 3행씩 update

| **id** | **bid_id** | **entity_id** | **quantity_kwh** | **bid_price** | **result** |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | 1 | 0.35 | 124 | rejected |
| 2 | 1 | 2 | 0.30 | 123 | accepted |
| 3 | 1 | 3 | 0.20 | 122 | accepted |
| 4 | 2 | 1 | null | null | null |
| 5 | 2 | 2 | 0.5 | 140 | rejected  |
| 6 | 2 | 3 | null | null | null |

### 입찰 제안 시 프롬프트에 들어갈 재료 테이블 (node_status_log와 함께 아래 테이블이 LLM 프롬프트에 들어감)

### 4. `weather` – 날씨 데이터 [SQL→ LLM]

| **칼럼명** | **설명** |
| --- | --- |
| obs_time | 관측 또는 예측 기준시간 (YYYY-MM-DD HH:00:00) |
| temperature_c | 기온 (°C) |
| rainfall_mm | 강수량 (mm) |
| humidity_pct | 습도 (%) |
| cloud_cover_okta | 운량 (0~10 점) |
| solar_irradiance | 일사량 (MJ/m² 또는 W/m², 단위 일관성주요!) |
| wind_speed | 풍속 (m/s) |

예시)

| **obs_time** | **temperature_c** | **rainfall_mm** | **humidity_pct** | **cloud_cover_okta** | **solar_irradiance** | wind_speed |
| --- | --- | --- | --- | --- | --- | --- |
| 2024-05-31 00:00 | 19.0 | 1.2 | 81 | 10 | 446 | 3.1 |
| 2024-05-31 01:00 | 18.7 | 0.9 | 85 | 10 | 446 | 2.8 |
| 2024-05-31 02:00 | 18.5 | 0.3 | 81 | 10 | 446 | 2.5 |
| 2024-05-31 03:00 | 18.2 | 0 | 83 | 10 | 446 | 2.1 |

### 5. `smp` –smp 시간별 데이터 [SQL→ LLM & LLM → 백엔드 ]

| **칼럼명** | **설명** |
| --- | --- |
| smp_time | 적용 시각 (YYYY-MM-DD HH:00:00) |
| price_krw | 해당 시각의 SMP 값 (원/kWh) |

예시) 제주 24년도 5월 31일 csv 참조

| **smp_time** | **price_krw** |
| --- | --- |
| 2024-05-31 00:00 | 128.2 |
| 2024-05-31 01:00 | 127.6 |
| 2024-05-31 02:00 | 122.9 |
| 2024-05-31 03:00 | 118.0 |

### 6. `profit_log` – 수익 로그 (20초마다 업데이트 - node_status_log 업데이트 시간에 맞춤)

| **럼명** | **타입** | **설명** |
| --- | --- | --- |
| id | INT (PK) | 고유번호 |
| profit_timestamp | DATETIME | 정산 시간 (=실시간 거래 시각) |
| entity_id | INT (FK) | 설비(발전소/배터리) ID |
| unit_price | FLOAT | 거래 단가 (원/kWh) |
| revenue_krw | FLOAT | 실현 수익(=현재 발전량×unit_priceX 20초) 20초마다 발생하는 수익 |

# REST API 설계

![rest api 구조.png](vpp/readme 자료/rest_api_구조.png)

### 1. 프론트 ↔ 서버

| 목적 | 메소드/엔드포인트 | 설명 |
| --- | --- | --- |
| 입찰 전략 확인 | `GET/serv_fr/generate_bid` | 입찰 로그 시각화용 |
| 입찰 제안 수정 및 최종 결정(진행) | `PUT/fr_serv/bid_edit_fix` | 1. 수정 없이 진행
2. 수정 하고 진행
3. 사용자 응답 없음
user의 input을 읽어와서 수정 or 최종 진행 입찰을 server로 보내는 역할 |
| 최종 입찰 결과 전송 | `GET/serv_fr/bidding_result` | 입찰 결과 시각화용(front용) |
| 발전소 결과 전송 | `GET/serv_fr/node_status` | DB에서 각 발전소별 실시간 발전량 데이터 반환 (프론트 그래프 용) |
| 수익 결과 전송 | `GET/serv_fr/profit` | DB에서 계산된 총발전량과 수익 정보 반환 (프론트 수익표 용) |

### 2. LLM ↔ 서버

| 목적 | 메소드/엔드포인트 | 설명 |
| --- | --- | --- |
| LLM이 출력한 입찰 전략을 서버에 전달 | `POST /llm_serv/generate_bid` |  bidding_log테이블에 3행(태양광, 풍력,배터리) 입찰을 한번에 저장 |
| 자원 상태 전체를 LLM에 제공 | `GET /llm_serv/node_status` | 입찰 전략 생성을 위한 태양광, 풍력, 배터리 자원 상태 전체를 LLM에 제공 |
| 입찰 전략 수립을 위한 최근 SMP(시장가격) 데이터 조회 | `GET /llm_serv/get_smp` |  |
|  기상 관측 데이터 반환 | `GET /llm_serv/get_weather` |  |

### 3. 아두이노 ↔ 서버

| API 영역 | 목적 | 메소드/엔드포인트 | 설명 |
| --- | --- | --- | --- |
| **아두이노 → 서버** | 발전/배터리 실시간 상태 전송 
(20초마다) | `POST/ardu_serv/node_status` | 아두이노가 현재 발전량, SOC, 전압 등 전송 |
| **서버 → 아두이노** | 명령 가져오기
(입찰 수락시) | `GET/serv_ardu/command` | 아두이노가 거래 성공/실패에 따라 릴레이 on/off 변경 |

# Open API 활용

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
    
