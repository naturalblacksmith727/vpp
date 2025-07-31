#!/bin/bash

while true; do
    echo ">>> 파이프라인 실행: $(date)"
    python3 vpp_bid_pipeline.py
    echo ">>> 15분 대기 중..."
    sleep 900
done

