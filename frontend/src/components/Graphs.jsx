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

    // 이후 20초마다 fetchData 반복 실행
    const interval = setInterval(fetchData, 20000); // 20초

    return () => clearInterval(interval);
  }, []);

  // 시간대별 온도
  const sunData = nodeData
    ? nodeData.solar.map((item) => ({
        시간: item.timestamp.slice(11, 16),
        생산전력량: item.power_kw,
      }))
    : [];

  const windData = nodeData
    ? nodeData.wind.map((item) => ({
        시간: item.timestamp.slice(11, 16),
        생산전력량: item.power_kw,
      }))
    : [];
  const batteryData = nodeData
    ? nodeData.battery.map((item) => ({
        시간: item.timestamp.slice(11, 16),
        충전전력량: item.power_kw,
      }))
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
              data={sunData}
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
                  value: "충전 전력량",
                  position: "insideTopLeft",
                  offset: 0,
                  dy: -20,
                }}
              />
              <Tooltip />
              <Line type="monotone" dataKey="충전전력량" stroke="#8884d8" />
            </LineChart>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Graphs;
