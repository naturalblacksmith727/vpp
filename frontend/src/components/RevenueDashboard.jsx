import axios from "axios";
import React, { useEffect, useState, useRef } from "react";

function RevenueDashboard() {
  return (
    <div className="fixed right-4 border border-gray-300 p-4 rounded-lg mt-16">
      <h2 className="text-2xl font-bold mt-1 mb-3 my-11 ">
        <p>실시간 수익현황</p>
        <p>(15분간)</p>
      </h2>
      <div>
        <div className="flex justify-center gap-6 mb-4">
          <div className="border p-4 rounded shadow-md bg-white">
            <h3 className="text-2xl font-bold mb-5">총 수익현황</h3>
            <p>총 발전량 : xxx kWh</p>
            <p>총 수익 : x,xxx원</p>
          </div>
        </div>
      </div>
    </div>
  );
}
export default RevenueDashboard;
