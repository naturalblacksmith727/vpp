import axios from "axios";
import React, { useEffect, useState, useRef } from "react";

function RevenueDashboard() {
  const [profitData, setprofitData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = () => {
      axios
        .get("https://aivpp.duckdns.org/api/serv_fr/profit")
        .then((response) => {
          if (response.data.status === "success") {
            setprofitData(response.data);
          } else {
            setError("데이터를 가져오지 못했습니다.");
          }
        })
        .catch((err) => {
          console.error(err);
          setError("서버 연결에 실패했습니다.");
        });
    };

    // 페이지 로드시 최초 1회 데이터 가져오기
    fetchData();

    // 이후 15분마다 fetchData 반복 실행
    const interval = setInterval(fetchData, 900000);

    return () => clearInterval(interval);
  }, []);

  if (!profitData) {
    return <p>데이터 로딩 중...</p>;
  }
  // 총 누적 발전량
  const total_generation_kwh = profitData.data.total_generation_kwh;
  // 총 누적 수익
  const total_revenue_krw = profitData.data.total_revenue_krw;

  return (
    <div className="fixed top-20 right-6 border border-gray-300 p-4 rounded-lg  z-50 bg-white shadow-md">
      <h2 className="text-2xl font-bold mt-1 mb-3 my-11 ">
        <p>총 누적 수익현황</p>
      </h2>
      <div>
        <div className="flex justify-center gap-6 mb-4">
          <div className="border p-4 rounded shadow-md bg-white">
            <p>
              총 발전량 : <br />
              {total_generation_kwh !== null &&
              total_generation_kwh !== undefined
                ? `${total_generation_kwh} kWh`
                : "데이터 없음"}
            </p>
            <br />
            <p>
              총 수익 : <br />
              {total_revenue_krw !== null && total_revenue_krw !== undefined
                ? `${total_revenue_krw} 원`
                : "데이터 없음"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
export default RevenueDashboard;
