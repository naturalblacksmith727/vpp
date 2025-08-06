// utils/fetchLatestBidResult.js
import axios from "axios";

export async function LatestBidResultMessage(setMessages) {
  try {
    const res = await axios.get(
      "https://aivpp.duckdns.org/api/serv_fr/bidding_result"
    );
    if (res.data.status === "success" && res.data.bid) {
      const entityMap = {
        1: "태양광",
        2: "풍력",
        3: "배터리",
      };

      const resultText = res.data.bid
        .map((item) => {
          const name = entityMap[item.entity_id];
          const status = item.result === "accepted" ? "✅ 수락" : "❌ 거절";
          const price = item.bid_price.toFixed(2);
          return `[${name}]\n결과: ${status}\n입찰가: ${price}원/kWh`;
        })
        .join("\n\n");

      setMessages((prev) => [
        ...prev,
        {
          sender: "bot",
          text: `[이전 입찰 결과 안내]\n\n${resultText}`,
          timestamp: new Date().toLocaleTimeString("ko-KR", {
            hour: "2-digit",
            minute: "2-digit",
          }),
        },
      ]);
    } else {
      setMessages((prev) => [
        ...prev,
        {
          sender: "bot",
          text: "최근 입찰 결과를 불러올 수 없습니다.",
          timestamp: new Date().toLocaleTimeString("ko-KR", {
            hour: "2-digit",
            minute: "2-digit",
          }),
        },
      ]);
    }
  } catch (err) {
    setMessages((prev) => [
      ...prev,
      {
        sender: "bot",
        text: "서버 에러로 입찰 결과를 가져올 수 없습니다.",
        timestamp: new Date().toLocaleTimeString("ko-KR", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      },
    ]);
  }
}
export default LatestBidResultMessage;
