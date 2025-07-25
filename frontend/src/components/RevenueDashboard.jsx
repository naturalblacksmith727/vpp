import axios from "axios";
import React, { useEffect, useState, useRef } from "react";

function RevenueDashboard() {
  return (
    <div className="fixed top-20 right-6 border border-gray-300 p-4 rounded-lg  z-50 bg-white shadow-md">
      <h2 className="text-2xl font-bold mt-1 mb-3 my-11 ">
        <p>실시간 수익현황</p>
        <p>(15분간)</p>
      </h2>
      <div>
        <div className="flex justify-center gap-6 mb-4">
          <div className="border p-4 rounded shadow-md bg-white">
            <p>총 발전량 : xxx kWh</p>
            <p>총 수익 : x,xxx원</p>
          </div>
        </div>
      </div>
    </div>
  );
}
export default RevenueDashboard;
