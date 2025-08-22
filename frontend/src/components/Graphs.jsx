import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  CartesianGrid,
  ReferenceArea,
  Label,
} from "recharts";
import axios from "axios";
import React, { useEffect, useState } from "react";

function Graphs() {
  const [nodeData, setNodeData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = () => {
      axios
        .get("https://aivpp.duckdns.org/api/serv_fr/node_status")
        //.get("/api/serv_fr/node_status")
        .then((response) => {
          if (response.data.status === "success") {
            setNodeData(response.data.data);
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

    // 이후 60초마다 fetchData 반복 실행
    const interval = setInterval(fetchData, 60000); // 60초

    return () => clearInterval(interval);
  }, []);

  // 시간대별로 생산전력량 합산하는 함수
  const sumByTime = (data, keyName) => {
    const grouped = {};

    data.forEach((item) => {
      // HH:mm 포맷으로 시간만 추출
      const time = item.timestamp.slice(11, 16);
      if (!grouped[time]) {
        grouped[time] = 0;
      }
      grouped[time] += item.power_kw;
    });

    // 그래프용 배열로 변환
    return Object.entries(grouped).map(([time, value]) => ({
      시간: time,
      [keyName]: Number(value.toFixed(6)),
    }));
  };

  // 시간대별 태양광
  const solarData = nodeData
    ? sumByTime(nodeData.solar, "생산전력량", "power_kw")
    : [];

  const windData = nodeData
    ? sumByTime(nodeData.wind, "생산전력량", "power_kw")
    : [];
  const batteryData = nodeData
    ? Object.values(
        nodeData.battery.reduce((acc, item) => {
          const time = item.timestamp.slice(11, 16);
          acc[time] = { 시간: time, 현재충전상태: item.soc }; // 같은 시간대면 마지막 값으로 덮어쓰기
          return acc;
        }, {})
      )
    : [];

  if (!nodeData) {
    return <p>데이터 로딩 중...</p>;
  }

  return (
    <div className="w-full px-4 border border-gray-300 rounded-lg">
      <h2 className="text-4xl font-bold mt-11 mb-11 my-11 ">
        실시간 발전 현황 그래프
      </h2>
      <div className="w-full px-16 grid grid-cols-2 gap-16 justify-items-center ">
        <div>
          <h3 className="text-2xl font-bold  mb-4 pl-10">태양광</h3>
          <div className="flex flex-col items-center">
            <LineChart
              width={450}
              height={300}
              data={solarData}
              margin={{ top: 30, right: 20, bottom: 20, left: 40 }}
            >
              <CartesianGrid
                vertical={false}
                stroke="#ccc"
                strokeDasharray="3 3"
              />
              <XAxis
                dataKey="시간"
                label={{
                  value: "시간",
                  position: "insideBottomRight",
                  offset: -5,
                }}
              />
              <YAxis
                label={{
                  value: "생산 전력량",
                  position: "insideTopLeft",
                  offset: 0,
                  dy: -20,
                }}
              />
              <Tooltip />
              <Line type="monotone" dataKey="생산전력량" stroke="#8884d8" />
            </LineChart>
          </div>
        </div>
        <div>
          <h3 className="text-2xl font-bold  mb-4 pl-10">풍력</h3>
          <div className="flex flex-col items-center">
            <LineChart
              width={450}
              height={300}
              data={windData}
              margin={{ top: 30, right: 20, bottom: 20, left: 40 }}
            >
              <CartesianGrid
                vertical={false}
                stroke="#ccc"
                strokeDasharray="3 3"
              />
              <XAxis
                dataKey="시간"
                label={{
                  value: "시간",
                  position: "insideBottomRight",
                  offset: -5,
                }}
              />
              <YAxis
                label={{
                  value: "생산 전력량",
                  position: "insideTopLeft",
                  offset: 0,
                  dy: -20,
                }}
              />
              <Tooltip />
              <Line type="monotone" dataKey="생산전력량" stroke="#8884d8" />
            </LineChart>
          </div>
        </div>
        <div>
          <h3 className="text-2xl font-bold  mb-4 pl-10">배터리</h3>
          <div className="flex flex-col items-center">
            <LineChart
              width={450}
              height={300}
              data={batteryData}
              margin={{ top: 30, right: 20, bottom: 20, left: 40 }}
            >
              <CartesianGrid
                vertical={false}
                stroke="#ccc"
                strokeDasharray="3 3"
              />
              <XAxis
                dataKey="시간"
                label={{
                  value: "시간",
                  position: "insideBottomRight",
                  offset: -5,
                }}
              />
              <YAxis
                label={{
                  value: "현재충전상태",
                  position: "insideTopLeft",
                  offset: 0,
                  dy: -20,
                }}
              />
              <Tooltip />
              <Line type="monotone" dataKey="현재충전상태" stroke="#8884d8" />
            </LineChart>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Graphs;
