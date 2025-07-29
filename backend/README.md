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
