# 백엔드 구조
[서버 시작]
    │
    ▼
app.py 실행 → Flask 서버 시작
         └── vpp_api.py의 모든 API 등록
         └── tasks.py의 주기적 작업 등록 및 실행

[Postman에서 API 호출]
    └→ vpp_api.py 내부 라우터 실행

[자동 작업]
    └→ 15분마다: evaluate_bids() → 입찰 평가 → bidding_result에 저장
    └→ 20초마다: calculate_profit() → 실시간 수익 계산 → profit_log에 저장


# REST API spec

## 프론트↔서버 ↔ LLM

![rest api 구조.png](REST%20API%20spec%20233c8e843beb80f39e6deb7aabe9be3d/rest_api_%E1%84%80%E1%85%AE%E1%84%8C%E1%85%A9.png)

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

### 입찰 전략 확인 GET/serv_fr/generate_bid

- 엔드포인트 : GET/serv_fr/generate_bid
- llm이 테이블 업데이트 → 서버가 업데이트된 테이블을 프론트로.
- 목적 : 서버가 자동 생성한 입찰 데이터를 프론트에 보여줌
    - Response
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | fail_reason | string/null | 실패 사유/null |
        | bids | array | 입찰 항목 배열/null |
        | ㄴentity_id | int | 발전소 id(태양광 등) |
        | ㄴbid_time  | string | 입찰 시각 |
        | ㄴbid_price_per_kwh | float | llm 입찰 제안 가격 (원/kWh) |
        | ㄴbid_quantity_kwh | float | llm 입찰 제안 전력량 (kWh) |
        | ㄴllm_reasoning | string | llm 전략 요약 |
        - 성공 시
            
            ```json
            {
            	"fail_reason": null,
              "bids": [
                {
            	    "entity_id": 1
                  "bid_time": "2025-07-22 14:30:00 ",  // 입찰 시각
                  "bid_price_per_kwh": 52.0,                   // 입찰가 (원/kWh)
                  "bid_quantity_kwh": 5.0                  // 입찰 전력량 (kWh)
                  "llm_reasoning": "태양광 예측량이 높아 입찰 제안"
                },
                ...
              ]
            }
            ```
            
        - 실패 시
            
            ```json
            {
            	"fail_reason": "No LLM output: Failed to generate bidding strategy",
              "bids": null
            }
            ```
            
            - 실패 사유
            
            | 상황 | 예시 메시지 (fail_reason) |
            | --- | --- |
            | LLM 결과 없음 | "No LLM output: Failed to generate bidding strategy" |
            | 내부 에러 | "Internal server error during bid generation" |

### 사용자 응답 처리 및 최종 입찰 확정 PUT/fr_serv/bid_edit_fix

- 엔드포인트 : PUT/fr_serv/bid_edit_fix
- 목적 : 사용자의 입찰 수락/수정/응답 없음에 따라 서버에 전달
    - Request Body
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | action | enum | edit, confirm, timeout |
        | bid | array | 수정된 입찰 정보 (price, quantity) |
        | └ entity_name | enum | 태양광, 풍력, 배터리 |
        | └ bid_price_per_kwh | float | 사용자 제안 입찰 가격 (원/kWh) |
        
        ```json
        {
          "action": "edit",                    // "edit" | "confirm" | "timeout"
          "bid": {
        	  "entity_name" : "태양광",
            "bid_price_per_kwh": 55.0                    // 수정된 가격
          }
        }
        ```
        
        - action
            - edit : 사용자가 값을 수정하고 제출
            - confirm : 서버 제안값 그대로 사용
            - timeout : 사용자 반응 없음 → 서버가 자동 진행
    - Response
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | status | enum | “Success” or “failed” |
        | action | enum | edit, confirm, timeout, server |
        | fail_reason | string | 실패 사유/null |
        - 성공 시
            
            ```json
            { 
            	"status": "Success",
            	"action" : "edit",
            	"fail_reason" : null
            }
            ```
            
        - 실패 시
            
            ```json
            { 
            	"status": "failed",
            	"action" : "edit",
            	"fail_reason" : "Missing bid data: Price or entity not provided"
            }
            ```
            
            - 실패 사유
                
                
                | 액션 타입 | 상황 (한글) | 예시 메시지 (fail_reason, 영어) |
                | --- | --- | --- |
                | edit | 수정 데이터 누락 | Missing bid data: Price or entity not provided |
                | edit | 허용되지 않은 entity | Invalid entity: Must be one of ['태양광', '풍력', '배터리'] |
                | edit | DB 저장 실패 | Failed to save user edit: Database error |
                | confirm | 기존 입찰 데이터 없음 | Cannot confirm: No existing bid data found |
                | confirm | DB 업데이트 실패 | Confirmation failed: Unable to update bidding record |
                | timeout | LLM 입찰 제안 미존재 | Timeout fallback failed: No auto-generated bid found |
                | timeout | DB 쓰기 실패 | Timeout processing failed: Could not write default bid |
                | server | 내부 서버 오류 | Internal server error while processing user response |

### 입찰 결과 확인 GET/serv_fr/bidding_result

- 엔드포인트 : GET/serv_fr/bidding_result
- 목적: 입찰 결과 시각화 (입찰 성공 여부, 체결 가격, 수량)
    - Response
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | status | string | 입찰 결과 잘 조회했는지 여부 “success”, “failed” |
        | bid | array | 입찰 결과 배열 |
        | └ entity_id | int(FK) | 설비(발전소/배터리) ID |
        | └ bid_result | enum | 'accepted' 또는 'rejected' |
        | └ unit_price | float | 체결 가격 |
        | fail_reason | string | 입찰 결과 실패 이유/null |
        - 성공 시
            
            ```json
            {
            	"status" : "success",
            	"bid" : {
            	"entity_id" : 3
              "bid_result": "rejected",            // 'accepted' 또는 'rejected'
              "unit_price": 53.2              // 체결된 거래 가격
              },
              "fail_reason": null
            }
            ```
            
        - 실패 시
            - 실패 코드
                
                
                | 실패 사유 코드 | 설명 |
                | --- | --- |
                | missing_field:<field> | 필수 필드 누락 |
                | server_error | 서버 내부 문제 |
                
                ```json
                {
                	"status" : "success",
                	"bid" : null,
                  "fail_reason": <실패 원인>
                }
                ```
                

### 발전소 결과 요청 GET/serv_fr/node_status

- 엔드포인트 : GET/serv_fr/node_status
- 단위 시간: 20초
- 목적: DB에서 각 발전소별 실시간 발전량 데이터 반환 (프론트 그래프 용)
    - Response
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | `status` | string | "success", “failed” |
        | `data` | object | 설비 유형별 상태 데이터 |
        | └ `solar` | array | 태양광 설비의 상태 리스트 |
        | └ `wind` | array | 풍력 설비의 상태 리스트 |
        | └ `battery` | array | 배터리 상태 리스트 |
        | 각 설비 내부 필드 |  |  |
        | └ `relay_id` | int | 설비 ID (`node_status_log.relay_id`) |
        | └ `power_kw` | float | 실시간 전력량 |
        | └ `soc` | float/null | 충전 상태(%) – 배터리만 값 존재 |
        | `timestamp` | datetime | 측정 시각 (`node_timestamp`) |
        | `fail_reason` | null | 실패 사유 (없음) |
        - 성공 시
            
            ```json
            {
              "status": "success",
              "data": {
                "solar": [
                  { "relay_id": 1, "power_kw": 0.45, "soc": null },
                  { "relay_id": 4, "power_kw": 0, "soc": null }
                ],
                "wind": [
                  { "relay_id": 2, "power_kw": 0, "soc": null },
                  { "relay_id": 5, "power_kw": 0.15, "soc": null }
                ],
                "battery": [
                  { "relay_id": 3, "power_kw": 0.2, "soc": 68.2 },
                ]
              },
              "timestamp": "2025-07-23T13:45:00",
              "fail_reason": null
            }
            
            ```
            
        - 실패 시
            - 실패 코드
                
                
                | 실패 사유 코드 | 설명 |
                | --- | --- |
                | no_data_available | 최근 기준 node_status_log 데이터가 없음 |
                | server_error | 서버 내부 문제 |
                
                ```json
                {
                  "status": "failed",
                  "data": null,
                  "timestamp": null,
                  "fail_reason": 실패 이유
                }
                ```
                

### 수익 결과 요청 GET/serv_fr/profit

- 엔드포인트 : GET/serv_fr/profit
- 단위 시간: 15분 단위
- 목적: DB에서 계산된 총발전량과 수익 정보 반환 (프론트 수익표 용)
    - Response
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | `status` | string | "success" 또는 "failed" |
        | `data` | array | 누적 총 수익, 총 발전량 배열 |
        | `data.total_revenue_krw` | float | 누적 수익 (원) – `profit_log` 기준 |
        | `data.total_generation_kwh` | float | 누적 발전량 (kWh) – `node_status_log` 기준 |
        | `fail_reason` | string/null | 실패 사유 (예: 파라미터 누락, DB 오류 등) |
        - 성공 시
            
            ```json
            {
              "status": "success",
              "data": {
                "total_revenue_krw": 12485.6,      // 누적 총 수익 (원)
                "total_generation_kwh": 122.35     // 누적 총 발전량 (kWh)
              },
              "fail_reason": null
            }
            ```
            
        - 실패 시
            - 실패 코드
                
                
                | 실패 사유 코드 | 설명 |
                | --- | --- |
                | missing_field:<field> | 필수 필드 누락 |
                | server_error | 서버 내부 문제 |
                
                ```json
                {
                  "status": "failed",
                  "data": null,
                  "timestamp": null,
                  "fail_reason": "missing_parameter:from"
                }
                ```
                
        - 내부 로직 계산 예시
            - 누적 발전량
            
            ```sql
            SELECT SUM(power_kw * (20.0 / 3600))
            FROM node_status_log
            WHERE relay_id IN (1,2,4,5)
            AND node_timestamp BETWEEN {from} AND {to}
            ```
            
            - 누적 수익
            
            ```sql
            SELECT SUM(revenue_krw)
            FROM profit_log
            WHERE profit_timestamp BETWEEN {from} AND {to}
            ```
            

### 2. LLM ↔ 서버

### 입찰 전략 기록 POST /llm_serv/generate_bid

- endpoint : `POST /llm_serv/generate_bid`
- 타이밍 : AI로 전량 생성이 완료 되었을 때
- 목적 : LLM이 출력한 입찰 전략을 서버에 전달하여 bidding_log테이블에 3행(태양광, 풍력,배터리)를 한번에 저장
    - Request Body (JSON)
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | bid_time | string | 입찰 적용 시간 (예: “2025-07-22T11:15:00”) |
        | bid_id | int | 동일 시간대 전략 묶음 식별자 |
        | bids | array | 자원별 입찰 전략 목록 (총 3개: 태양광/풍력/배터리) |
        | ㄴresource_type | string | `"태양광"`, `"풍력"`, `"배터리"` 중 하나 |
        | ㄴentity_id | int | 해당 자원에 연결된 설비 ID |
        | ㄴbid_quantity_kwh | float / null | 입찰 용량 (kW 단위)
        * “입찰 비권장” 인 경우 null |
        | ㄴbid_price_per_kwh | float / null | 입찰 가격 (원/kWh)
        * “입찰 비권장” 인 경우 null |
        | ㄴrecommendation | string | 입찰 권장 여부 (예: “입찰권장”, “입찰비권장”) |
        | ㄴllm_reasoning | string | 판단 근거 요약 (예: “SMP 상승 + SOC 여유”) |
        
        ```python
        {
          "bid_time": "2025-07-22T11:15:00",
          "bid_id": 27,
          "bids": [
            {
              "resource_type": "태양광",
              "entity_id": 1,
              "bid_quantity_kwh": 0.38,
              "bid_price_per_kwh": 124,
              "recommendation": "입찰 권장",
              "llm_reasoning": "일사량이 높고 SMP가 상승세이므로 수익성 확보 가능"
            },
            {
              "resource_type": "풍력",
              "entity_id": 2,
              "bid_quantity_kwh": 0.35,
              "bid_price_per_kwh": 123,
              "recommendation": "입찰 권장",
              "llm_reasoning": "풍속이 안정적이며 현재 SMP 수준에서 수익 기대"
            },
            {
              "resource_type": "배터리",
              "entity_id": 3,
              "bid_quantity_kwh": null,
              "bid_price_per_kwh": null,
              "recommendation": "입찰 비권장",
              "llm_reasoning": "SOC가 낮아 방전 불가"
            }
          ]
        }
        
        ```
        
    - Response Body
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | result | string | “Success” or “Failed” |
        | message | string | 처리 메세지 (성공 시) |
        | reason | string | 실패 원인 (실패 시) |
        - 성공 시
            
            ```python
            {
            "result": "Success",
            "message": "입찰 전략 저장 완료"
            }
            ```
            
        - 실패 시
            
            
            | **코드** | **설명** | **예시 응답 (`reason`)** |
            | --- | --- | --- |
            | `missing_field:<field>` | 필수 필드 누락 | `"missing_field:bid_time"` |
            | `invalid_format:<field>` | 필드 포맷 불일치 (예: 날짜 형식, 리스트 아님) | `"invalid_format:bid_time (must be ISO 8601)"` |
            | `invalid_type:<field>` | 잘못된 타입 (예: float이어야 하는데 string 등) | `"invalid_type:bid_quantity_kwh (must be float or null)"` |
            | `empty_bid_list` | 입찰 리스트가 빈 배열이거나 빈 필드가  있은 | `"empty_bid_list"` |
            | `sql_insert_error` | DB insert 실패 (예: FK 오류, null 삽입 불가 등) | `"sql_insert_error: foreign key constraint fails"` |
            | `db_connection_error` | DB 연결 문제 | `"db_connection_error"` |
            | `internal_server_error` | 알 수 없는 서버 내부 오류 | `"internal_server_error"` |
            
            ```python
            {
              "result": "Failed",
              "reason":"missing field:bid_time"
            }
            ```
            

### 현재 발전량 요청 GET /llm_serv/node_status

- endpoint : `GET /llm_serv/node_status`
- 타이밍 : 입찰 전량 생성 전 15분 단위로
- 목적 : 입찰 전략 생성을 위한 태양광, 풍력, 배터리 자원 상태 전체를 LLM에 제공
    - Request Boby (JSON)
        - 없음
        - 서버는 내부적으로 `node_status_log`에서 자원별로 최신 측정값을 조회함
        - `relay_id` 기준 자원 매핑
            
            
            | relay_id | 자원 유형 |
            | --- | --- |
            | 1, 4 | 태양광 |
            | 2, 5 | 풍력 |
            | 3 | 배터리 |
    - Response Body
        
        
        | **필드명** | **타입** | **설명** |
        | --- | --- | --- |
        | result | string | 성공 실패 여부 |
        | `timestamp` | string | 전체 데이터의 기준 시각 (예: `"2025-07-23T11:00:00"`) |
        | `resources` | array | 각 자원의 상태 정보 리스트 |
        | └ `type` | string | 자원 종류: `"태양광"` / `"풍력"` / `"배터리"` |
        | └ power`_kw` | float | 현재 발전량 또는 방전량 (kW 단위) |
        | └ `status` | string | 자원 상태 설명 (`"방전 가능"`, `“방전 불가능”` `"SOC 낮음"`, `“SOC 높음”`  ) |
        | └ `solar_irradiance` | int | **[태양광 전용]** 일사량 (W/m²) |
        | └ `wind_speed` | float | **[풍력 전용]** 풍속 (m/s) |
        | └ `soc` | float | **[배터리 전용]** 충전 상태 (State of Charge, %) |
        - 성공 시
            
            ```python
            {
            	"result": "sucess",
              "timestamp": "2025-07-23T11:00:00",
              "resources": [
                {
                  "type": "태양광",
                  "power_kw": 0.38,
                  "solar_irradiance": 690,
                  "status": "정상"
                },
                {
                  "type": "풍력",
                  "power_kw": 0.36,
                  "wind_speed": 3.8,
                  "status": "정상"
                },
                {
                  "type": "배터리",
                  "power_kw": 0.15,
                  "soc": 67,
                  "status": "방전 가능"
                }
              ]
              }
            
            ```
            
        - 실패 시
            
            
            | 실패 사유 코드 | 원인 설명 |  |
            | --- | --- | --- |
            | `no_data` | 자원 데이터가 전혀 없음 |  |
            | `db_error` | DB 연결 또는 쿼리 오류 |  |
            | `partial_missing` | 일부 자원 데이터 누락
            missing_fields에 누락된 필드명 | "missing_fields": ["solar_irradiance", "soc"] |
            
            ```json
            { "result": "Failed", 
            	"partial_missing":{
            		"missing_fields": ["solar_irradiance", "soc"]
            	}
            }
            
            ```
            

### SMP 데이터 요청 GET /llm_serv/get_smp

- endpoint : `GET /llm_serv/get_smp`
- 타이밍 : LLM이 전략 판단을 위해 시장 데이터를 파악할 때, 15분 단위로
- 목적 : 입찰 전략 수립을 위한 최근 SMP(시장가격) 데이터 조회
    - Request Body
        - 없음
        - 내부적으로 최근 4일치 SMP 평균 단가 또는 15분 단위 데이터 조회
        - timestamp에 따라 최근 4일치 같은 시점의 smp
    - Response Body
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | timestamp | sting | 기준 시간 (예: 가장 최근 데이터 시각)
        현재 시간 - 15분, 현재 시간, 현재 시간 + 15분, 현재 시간 +30분 |
        | smp_data | object | 날짜별 SMP 배열 (`YYYY-MM-DD`: [단가1, 단가2, ...]) |
        - 성공 시
            
            ```python
            {
              "timestamp": "2025-07-23T11:00:00",
              "smp_data": {
                "2025-07-20": [109.3, 110.1, 111.4, 112.0],
                "2025-07-21": [112.2, 113.5, 113.0, 111.8],
                "2025-07-22": [114.1, 115.6, 115.3, 113.9],
                "2025-07-23": [116.5, 117.0, 117.8, 118.2]
              }
            }
            ```
            
        - 실패 시
            
            
            | 실패 사유 코드 | 원인 | 예시 응답 메세지 |
            | --- | --- | --- |
            | no_data | 데이터 없음 | SMP data unvailable for requested period |
            | no_db_connection | DB 연결 오류 | Internal sever error during SMP data fetch |
            | invalid_format | 형식 오류 또는 파싱 실패 | Invalid SMP format in database |
            
            ```python
            {
              "result": "failed",
              "reason": "invalid_format"
            }
            ```
            

### 날씨 데이터 요청 GET/llm_serv/get_weather

- endpoint : `GET /llm_serv/get_weather`
- 타이밍 : LLM이 전략 판단을 위해 시장 데이터를 파악할 때
- **목적**: 입찰 시점(15분 단위) 기준으로 해당하는 1시간 단위 기상 관측 데이터 반환
- **설명**:
    - 기상 관측 데이터는 1시간 단위(`obs_time`)로 기록됨
    - 입찰은 15분 단위로 발생하므로, 요청 시점과 가장 가까운 1시간 단위 데이터를 조회하여 반환
    - AI 프롬프트 내 부가정보 생성에 활용
- Request Body
    - 입찰 시점을 요청
    
    | 필드명 | 타입 | 필수 여부 | 설명 |
    | --- | --- | --- | --- |
    | time | string | 필수 | 입찰 시점(ISO 8601 형식, 15분 단위 권장) |
    
    ```sql
    GET /llm_serv/weather?time=2025-07-22T11:15:00
    ```
    
- Response Body
    
    
    | 필드명 | 타입 | 설명 |
    | --- | --- | --- |
    | obs_time | string | 조회된 기상 데이터의 관측 시각 (1시간 단위) |
    | temperature_c | float | 기온 (섭씨 °C) |
    | rainfall_mm | float | 강수량 (mm) |
    | humidity_pct | int | 습도 (%) |
    | cloud_cover_okta | int | 구름 양 (okta 단위, 0~8) |
    | solar_irradiance | int | 일사량 (W/m²) |
    | wind_speed | float | 풍속 (m/s) |
    - 성공시
    
    ```json
    {
      "obs_time": "2025-07-22T11:00:00",
      "temperature_c": 25.3,
      "rainfall_mm": 0.0,
      "humidity_pct": 60,
      "cloud_cover_okta": 2,
      "solar_irradiance": 710,
      "wind_speed": 3.8
    }
    ```
    
    - 실패시
        
        
        | 실패 사유 코드 | 원인 | 예시 응답 메시지 |
        | --- | --- | --- |
        | `no_data` | 요청 시간대에 해당하는 기상 데이터 없음 | `No weather data available for requested time` |
        | `db_error` | DB 조회 중 내부 오류 발생 | `Internal server error during weather data fetch` |
        | `invalid_format` | 데이터 형식 오류 또는 파싱 실패 | `Invalid weather data format in database` |
        
        ```json
        {
          "result": "Failed",
          "reason": "No weather data available for requested time"
        }
        ```
        

## 아두이노 ↔ 서버

| API 영역 | 목적 | 메소드/엔드포인트 | 설명 |
| --- | --- | --- | --- |
| **아두이노 → 서버** | 발전/배터리 실시간 상태 전송 
(20초마다) | `POST/ardu_serv/node_status` | 아두이노가 현재 발전량, SOC, 전압 등 전송 |
| **서버 → 아두이노** | 명령 가져오기
(입찰 수락시) | `GET/serv_ardu/command` | 아두이노가 거래 성공/실패에 따라 릴레이 on/off 변경 |

### 발전소 및 배터리 실시간 상태 전송 POST/ardu_serv/node_status

- 엔드포인트 : POST/ardu_serv/node_status
- 주기 : 20초마다
- 목적 : 현재 발전 상태 및 배터리 정보 전송(서버는 이 데이터를 분석/기록/입찰 전략 반영 등에 사용)
    - Request Body(JSON)
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | relay_id | int | 장치 고유 식별자 |
        | node_timestamp | string | 상태 전송 시각 (예: `"YYYY-MM-DD HH:MM:SS"`) |
        | power_kw | float | 현재 발전/소비 전력(kW) |
        | soc | float\null | 배터리 잔량(%). 배터리일 경우만 입력. 나머지는 null |
        
        ```json
        {
          "relay_id": 1, // 태양-부하
          "node_timestamp": "2025-07-22 14:31:00",
          "power_kw": 0.1205,
          "soc": null
        }
        
        ```
        
        ```json
        {
          "relay_id": 5, // 풍력-배터리
          "node_timestamp": "2025-07-22 14:31:00",
          "power_kw": 0.1205,
          "soc": 83.2
        }
        
        ```
        
    - Response
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | result | enum | “Success” or “failed” |
        | node_timestamp | int | 저장된 시간(성공 시) |
        | reason | string | 실패 원인(실패 시) |
        - 성공
            
            ```json
            { "result": "Success", 
            	"node_timestamp": "2025-07-22 14:31:00",
            	"reason" : null
            }
            ```
            
        - 실패
            
            
            | 원인 | 예시 응답 |
            | --- | --- |
            | 필수 필드 누락 | Missing required field: power_kw |
            | 잘못된 데이터 타입 | Invalid type: soc must be float or null |
            | 서버 내부 오류 | Internal server error while saving node status |
            
            ```json
            { "result": "failed",
            	"node_timestamp" : "2025-07-22 14:31:00",
              "reason": "<실패 원인>" 
            }
            ```
            

### 릴레이 명령 전송 GET/serv_ardu/command

- 엔드포인트 : GET/serv_ardu/command
- 목적 : 입찰 성공/실패에 따라 릴레이(전력 송출 장치) 제어
    - Response
        
        
        | 필드명 | 타입 | 설명 |
        | --- | --- | --- |
        | status | string | “success” “failed” |
        | command | array | 제어 명령 항목  |
        | └ realy_id | int | 장치 고유 식별자 |
        | └ relay | enum | on, off |
        | └ reason | enum | “accepted”, “rejected” |
        | fail_reason | string/null | 명령 실패 시 사유(성공이면 null) |
        - 성공 시
            
            ```json
            {
            	"status" : "success",
            	"command":{
            	"relay_id": 1, //태양-부하
              "relay": "on",                         // 또는 "off"
              "reason": "accepted",
            	},
              "fail_reason" : null
            }
            ```
            
        - 실패 시
            
            ```json
            {
            	"status" : "failed",
            	"command": null,
              "fail_reason" : 실패 사유
            }
            ```
            
            - 실패 사유
                
                
                | 코드 | 설명 |
                | --- | --- |
                | relay not registered | relay_id가 시스템에 등록되지 않음 |
                | command conflict | 이전 명령이 아직 실행되지 않음 (중복 또는 충돌 방지 목적) |
                | internal server error | 서버 처리 중 오류 |
                | relay unavailable | 릴레이가 현재 물리적으로 연결되지 않았거나 통신 불가 |
                | entity inactive | 해당 엔티티(발전소/배터리)가 비활성 상태 |

⇒ 아두이노는 이 명령에 따라 릴레이를 켜거나 꺼서 실제 전력을 거래함