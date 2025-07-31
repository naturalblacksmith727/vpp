#!/bin/bash

while true; do
    echo ">>> 파이프라인 실행: $(date)"
    /opt/anaconda3/bin/python /Users/sohi/workspace/vpp/backend/vpp_bid_pipeline.py
    echo ">>> 15분 대기 중..."
    sleep 900
done

