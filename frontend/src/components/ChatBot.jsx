import axios from "axios";
import LoadingDots from "./LoadingDots";
import React, { useEffect, useState, useRef } from "react";
import LatestBidResultMessage from "./LatestBidResultMessage";

function ChatBot() {
  const [bidData, setBidData] = useState(null);
  const [resultData, setResultData] = useState(null);
  const [error, setError] = useState(null);
  const [isBiddingActive, setIsBiddingActive] = useState(false); // 입찰 활성화 상태

  const [messages, setMessages] = useState([
    {
      sender: "bot",
      text: `안녕하세요.
가상 발전소(vpp) AI 대화형 전략 어시스턴트입니다.
15분 간격으로 자원별 실시간 상태 요약, 시장 환경 분석, 추천 입찰 전략을 알려드립니다.
(00분, 15분, 30분, 45분)`,
      timestamp: new Date().toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
      }),
    },
  ]);

  const [input, setInput] = useState("");

  const messagesEndRef = useRef(null);
  const lastMinuteRef = useRef(null); // 시간 확인용
  const timeoutTimerRef = useRef(null); // 타임아웃 타이머
  const awaitingEditInputRef = useRef(false); // "수정하고진행" 상태 확인용

  // --- 메시지 지연 출력 함수 ---
  const addMessageWithDelay = (newMessage, delay = 30000) => {
    setTimeout(() => {
      setMessages((prev) => [...prev, newMessage]);
    }, delay);
  };

  useEffect(() => {
    const fetchData = () => {
      axios
        .get("https://aivpp.duckdns.org/api/serv_fr/generate_bid")
        .then((response) => {
          if (response.data.fail_reason === null) {
            setBidData(response.data);
          } else {
            setError("데이터를 가져오지 못했습니다.");
          }
        })
        .catch((err) => {
          console.error(err);
          setError("서버 연결에 실패했습니다.");
        });

      axios
        .get("https://aivpp.duckdns.org/api/serv_fr/bidding_result")
        .then((response) => {
          if (response.data.status === "success") {
            setResultData(response.data);
          } else {
            setError("데이터를 가져오지 못했습니다.");
          }
        })
        .catch((err) => {
          console.error(err);
          setError("서버 연결에 실패했습니다.");
        });
    };

    const now = new Date();
    const kstNow = new Date(
      now.toLocaleString("en-US", { timeZone: "Asia/Seoul" })
    );

    const minutes = kstNow.getMinutes();
    const seconds = kstNow.getSeconds();

    const nextQuarter = Math.ceil(minutes / 15) * 15;
    const waitMinutes = (nextQuarter - minutes + 60) % 60;

    const waitMs = (waitMinutes * 60 + (100 - seconds)) * 1000;

    fetchData();

    const timeout = setTimeout(() => {
      fetchData();
      const interval = setInterval(fetchData, 15 * 60 * 1000);
      timeoutTimerRef.current = interval;
    }, waitMs);

    return () => {
      clearTimeout(timeout);
      clearInterval(timeoutTimerRef.current);
    };
  }, []);

  const sendBidEditFix = async (action, bids = null) => {
    try {
      const response = await axios.put(
        "https://aivpp.duckdns.org/api/fr_serv/bid_edit_fix",
        { action, bids }
      );
      return response.data;
    } catch (error) {
      console.error("API 호출 실패", error);
      return { status: "failed", fail_reason: "서버 통신 오류" };
    }
  };

  const sendMessage = () => {
    if (!input.trim()) return;

    const userInput = input.trim();
    const normalizedInput = userInput.replace(/[\s;,]+/g, "");

    addMessageWithDelay({ sender: "user", text: userInput });
    setInput("");

    addMessageWithDelay({ sender: "bot", text: "답변 준비 중입니다..." }, 400);

    setTimeout(() => {
      (async () => {
        if (awaitingEditInputRef.current) {
          const matchAll =
            normalizedInput.matchAll(/(태양광|풍력|배터리)\s*(\d+)/g);
          const matches = Array.from(matchAll);

          if (matches.length > 0) {
            const nameToId = { 태양광: 1, 풍력: 2, 배터리: 3 };
            const editBids = matches
              .map(([_, entity_name, priceStr]) => {
                const entity_id = nameToId[entity_name];
                const matchedBid = bidData.bids.find(
                  (b) => b.entity_id === entity_id
                );
                return matchedBid
                  ? {
                      bid_id: matchedBid.bid_id,
                      entity_name,
                      entity_id,
                      bid_price_per_kwh: parseFloat(priceStr),
                    }
                  : null;
              })
              .filter((b) => b !== null);

            if (editBids.length === 0) {
              awaitingEditInputRef.current = false;
              addMessageWithDelay({
                sender: "bot",
                text: "입력한 항목에 해당하는 입찰 정보가 없습니다.",
                timestamp: new Date().toLocaleTimeString("ko-KR", {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              });
              return;
            }

            const edit_result = await sendBidEditFix("edit", editBids);

            awaitingEditInputRef.current = false;

            const successText = editBids
              .map((b) => `[${b.entity_name}] → ${b.bid_price_per_kwh}원/kWh`)
              .join("\n");

            addMessageWithDelay({
              sender: "bot",
              text:
                edit_result.status === "success"
                  ? `입찰가 수정 완료:\n${successText}\n\n입찰이 완료되었습니다.`
                  : `수정 실패: ${edit_result.fail_reason}`,
              timestamp: new Date().toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
            });
          } else {
            awaitingEditInputRef.current = false;
            addMessageWithDelay({
              sender: "bot",
              text: "형식이 잘못되었습니다. 예: '태양광 130'",
              timestamp: new Date().toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
            });
          }
          return;
        }

        if (normalizedInput == "수정없이진행") {
          if (!isBiddingActive) {
            addMessageWithDelay({
              sender: "bot",
              text: "입찰이 이미 종료되었습니다. \n다음 입찰 추천을 기다려주세요.",
              timestamp: new Date().toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
            });
            return;
          }

          if (timeoutTimerRef.current) clearTimeout(timeoutTimerRef.current);
          setIsBiddingActive(false);

          const result = await sendBidEditFix("confirm");

          addMessageWithDelay({
            sender: "bot",
            text:
              result.status === "success"
                ? "입찰이 완료되었습니다."
                : `오류: ${result.fail_reason}`,
            timestamp: new Date().toLocaleTimeString("ko-KR", {
              hour: "2-digit",
              minute: "2-digit",
            }),
          });
        } else if (normalizedInput == "수정하고진행") {
          if (!isBiddingActive) {
            addMessageWithDelay({
              sender: "bot",
              text: "입찰이 이미 종료되었습니다. \n다음 입찰 추천을 기다려주세요.",
              timestamp: new Date().toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
            });
            return;
          }

          if (timeoutTimerRef.current) clearTimeout(timeoutTimerRef.current);
          awaitingEditInputRef.current = true;
          setIsBiddingActive(false);

          addMessageWithDelay({
            sender: "bot",
            text: "수정할 항목을 입력해주세요.\n예: 태양광 130, 풍력 40, 배터리 0\n(입찰 거부시 0으로 표시)",
            timestamp: new Date().toLocaleTimeString("ko-KR", {
              hour: "2-digit",
              minute: "2-digit",
            }),
          });
        } else {
          addMessageWithDelay({
            sender: "bot",
            text: "올바른 명령어를 입력해주세요.\n(수정 없이 진행 / 수정하고 진행)",
            timestamp: new Date().toLocaleTimeString("ko-KR", {
              hour: "2-digit",
              minute: "2-digit",
            }),
          });
        }
      })();
    }, 2000);
  };

  useEffect(() => {
    const checkTimeAndSend = async () => {
      const now = new Date();
      const minutes = now.getMinutes();

      if ([0, 15, 30, 45].includes(minutes) && lastMinuteRef.current !== minutes && bidData) {
        lastMinuteRef.current = minutes;

        await LatestBidResultMessage(setMessages);

        setIsBiddingActive(true);

        const timestamp = now.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });

        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, "0");
        const day = String(now.getDate()).padStart(2, "0");
        const hour = String(now.getHours()).padStart(2, "0");
        const minute = String(now.getMinutes()).padStart(2, "0");
        const currtime = `${year}년 ${month}월 ${day}일 ${hour}:${minute}`;

        const entityType = { 1: "태양광", 2: "풍력", 3: "배터리" };

        const summary = bidData.bids
          .map((b) => `[${entityType[b.entity_id]}]\n- 입찰 전력량: ${b.bid_quantity_kwh}kWh\n- 입찰가 : ${b.bid_price_per_kwh}원/kWh\n${b.llm_reasoning}`)
          .join("\n\n");

        const newMessage = {
          sender: "bot",
          text: `[${currtime}]\n== 실시간 입찰 전략 ==\n\n${summary}\n\n해당 입찰을 수락하시겠습니까?\n(수정 없이 진행/ 수정하고 진행 입력)`,
          timestamp,
        };

        addMessageWithDelay(newMessage, 300);

        if (timeoutTimerRef.current) clearTimeout(timeoutTimerRef.current);
        timeoutTimerRef.current = setTimeout(async () => {
          const result = await sendBidEditFix("timeout");
          addMessageWithDelay({
            sender: "bot",
            text:
              result.status === "success"
                ? "응답이 없어 추천된 입찰을 모두 거부하였습니다."
                : `타임아웃 처리 실패: ${result.fail_reason}, ${result.action}`,
            timestamp: new Date().toLocaleTimeString("ko-KR", {
              hour: "2-digit",
              minute: "2-digit",
            }),
          });
          setIsBiddingActive(false);
        }, 300000);
      }
    };

    const interval = setInterval(checkTimeAndSend, 10000);
    return () => clearInterval(interval);
  }, [bidData]);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollTop = messagesEndRef.current.scrollHeight;
    }
  }, [messages]);

  if (!bidData) {
    return <p>데이터 로딩 중...</p>;
  }

  return (
    <div className="w-full px-4">
      <h2 className="mb-6 text-4xl font-bold text-center">챗봇 대화창</h2>

      <div className="w-full border border-gray-300 p-4 rounded-lg">
        <div
          className="h-96 overflow-y-auto border border-gray-300 rounded p-2"
          ref={messagesEndRef}
        >
          {messages.map((m, i) => (
            <div
              key={i}
              className={`my-2 flex ${m.sender === "user" ? "justify-end" : "justify-start"}`}
            >
              <div className="flex items-end max-w-full">
                <span
                  className={`inline-block px-4 py-2 rounded-xl whitespace-pre-wrap break-words max-w-full sm:max-w-[calc(100%-someMargin)] ${
                    m.sender === "user"
                      ? "bg-blue-500 text-white text-right"
                      : "bg-gray-200 text-black text-left"
                  }`}
                >
                  {m.text === "답변 준비 중입니다..." ? <LoadingDots /> : m.text}
                </span>
                <span className="ml-1 text-xs text-gray-400">{m.timestamp}</span>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="mt-4 flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            className="flex-grow px-4 py-2 border border-gray-300 rounded-md focus:outline-none"
            placeholder="메시지를 입력하세요"
            rows={2}
          />
          <button
            onClick={sendMessage}
            className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600"
          >
            전송
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatBot;
