import axios from "axios";
import React, { useEffect, useState, useRef } from "react";

function RevenueDashboard() {
  return (
    <div className="border border-gray-300 p-4 rounded-lg mb-12">
      <h2 className="text-4xl font-bold mt-11 mb-11 my-11 ">
        실시간 수익현황(15분 간격)
      </h2>
      <div>
        <div className="flex justify-center gap-6 mb-4">
          <div className="border p-4 rounded shadow-md bg-white">
            <h3 className="text-2xl font-bold mb-5">총 수익현황</h3>
            <p>총 발전량 : xxx kWh</p>
            <p>판매가 : xxx 원/kWh </p>
            <p>총 수익 : x,xxx원</p>
          </div>
          <div className="border p-4 rounded shadow-md bg-white">
            <h3 className="text-2xl font-bold mb-5">태양광 수익현황</h3>
            <p>태양광 발전량 : xxx kWh</p>
            <p>판매가 : xxx 원/kWh </p>
            <p>태양광 수익 : x,xxx원</p>
          </div>
          <div className="border p-4 rounded shadow-md bg-white">
            <h3 className="text-2xl font-bold mb-5">풍력 수익현황</h3>
            <p>풍력 발전량 : xxx kWh</p>
            <p>판매가 : xxx 원/kWh </p>
            <p>풍력 수익 : x,xxx원</p>
          </div>
          <div className="border p-4 rounded shadow-md bg-white">
            <h3 className="text-2xl font-bold mb-5">배터리 수익현황</h3>
            <p>배터리 충전량 : xxx kWh</p>
            <p>판매가 : xxx 원/kWh </p>
            <p>배터리 수익 : x,xxx원</p>
          </div>
        </div>
      </div>
    </div>
  );
}
export default RevenueDashboard;
