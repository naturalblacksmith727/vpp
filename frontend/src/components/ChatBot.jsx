import axios from "axios";
import LoadingDots from "./LoadingDots";
import React, { useEffect, useState, useRef } from "react";

function ChatBot() {
  const [bidData, setBidData] = useState(null);
  const [error, setError] = useState(null);
  const lastMinuteRef = useRef(null); // 시간 확인용

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
  const timeoutTimerRef = useRef(null); // 타임아웃 타이머

  useEffect(() => {
    const fetchData = () => {
      axios
        .get("https://aivpp.duckdns.org/api/serv_fr/generate_bid")
        //.get("127.0.0.1:5001/serv_fr/generate_bid")
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
    };
    // 페이지 로드시 최초 1회 데이터 가져오기
    fetchData();

    // 이후 10초마다 fetchData 반복 실행
    const interval = setInterval(fetchData, 10000); // 10000ms = 10초

    return () => clearInterval(interval);
  }, []);

  // bid_edit_fix 호출 함수
  const sendBidEditFix = async (action, bid = null) => {
    try {
      const response = await axios.put(
        "https://aivpp.duckdns.org/api/fr_serv/bid_edit_fix",
        {
          action,
          bid,
        }
      );
      return response.data;
    } catch (error) {
      console.error("API 호출 실패", error);
      return { status: "failed", fail_reason: "서버 통신 오류" };
    }
  };

  const sendMessage = () => {
    if (!input.trim()) return;

    // 사용자 메시지 추가
    const userInput = input.trim();
    setMessages((prev) => [...prev, { sender: "user", text: userInput }]);
    setInput("");

    // 봇 답변 준비중
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { sender: "bot", text: "답변 준비 중입니다..." },
      ]);
    }, 400);

    // 봇의 실제 답변 내용
    setTimeout(() => {
      (async () => {
        // 수정 없이 진행 입력시
        if (userInput == "수정 없이 진행") {
          const result = await sendBidEditFix("confirm");

          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = {
              sender: "bot",
              text:
                result.status === "success"
                  ? "수정 없이 입찰 완료"
                  : `오류: ${result.fail_reason}`,
              timestamp: new Date().toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
            };
            return newMessages;
          });
        } else if (userInput == "수정하고 진행") {
        }
        // 아무거나 입력했을시 출력
        else {
          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = {
              sender: "bot",
              text: "올바른 명령어를 입력해주세요(수정 없이 진행 / 수정하고 진행)",
              timestamp: new Date().toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
            };
            return newMessages;
          });
        }
      })();
    }, 2000);
  };
  // 시간마다 자동 메세지 전송
  useEffect(() => {
    const checkTimeAndSend = () => {
      const now = new Date();
      const minutes = now.getMinutes();

      // 00, 15, 30, 45분만, 중복 방지
      if (
        [0, 15, 30, 45].includes(minutes) &&
        lastMinuteRef.current !== minutes &&
        bidData
      ) {
        lastMinuteRef.current = minutes;

        const timestamp = now.toLocaleTimeString("ko-KR", {
          hour: "2-digit",
          minute: "2-digit",
        });

        const year = now.getFullYear(); // 2025
        const month = String(now.getMonth() + 1).padStart(2, "0"); // 07
        const day = String(now.getDate()).padStart(2, "0"); // 21
        const hour = String(now.getHours()).padStart(2, "0"); // 12
        const minute = String(now.getMinutes()).padStart(2, "0"); // 00
        const currtime = `${year}년 ${month}월 ${day}일 ${hour}:${minute}`;

        const entityType = { 1: "태양광", 2: "풍력", 3: "배터리" };

        const summary = bidData.bids
          .map((b) => {
            return `[${entityType[b.entity_id]}]\n- 입찰 전력량: ${
              b.bid_quantity_kwh
            }kWh\n- 입찰가 :${b.bid_price_per_kwh}원/kWh\n${b.llm_reasoning}`;
          })
          .join("\n\n");

        const newMessage = {
          sender: "bot",
          text: `[${currtime}]\n== 실시간 입찰 전략 ==\n\n${summary}\n\n해당 입찰을 수락하시겠습니까?\n(수정 없이 진행/ 수정하고 진행 입력)`,
          timestamp,
        };

        setMessages((prev) => [...prev, newMessage]);

        // === 타임아웃 타이머 설정 ===
        // 이전 타이머 제거
        if (timeoutTimerRef.current) clearTimeout(timeoutTimerRef.current);
        // 60초 후 타임아웃 전송
        timeoutTimerRef.current = setTimeout(async () => {
          const result = await sendBidEditFix("timeout");

          setMessages((prev) => [
            ...prev,
            {
              sender: "bot",
              text:
                result.status === "success"
                  ? "응답이 없어 기본 입찰로 진행했습니다."
                  : `타임아웃 처리 실패: ${result.fail_reason}`,
              timestamp: new Date().toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
            },
          ]);
        }, 60000); // 60초 후 타임아웃
      }
    };

    const interval = setInterval(checkTimeAndSend, 10000); // 10초마다 체크
    return () => clearInterval(interval);
  }, [bidData]);

  // 채팅창 자동으로 아래로 내리기
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
        {/* 메시지 출력 영역 */}
        <div
          className="h-96 overflow-y-auto border border-gray-300 rounded p-2"
          ref={messagesEndRef}
        >
          {messages.map((m, i) => (
            <div
              key={i}
              className={`my-2 flex  ${
                m.sender === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div className="flex items-end max-w-full">
                <span
                  className={`inline-block px-4 py-2 rounded-xl whitespace-pre-wrap break-words max-w-full sm:max-w-[calc(100%-someMargin)] ${
                    m.sender === "user"
                      ? "bg-blue-500 text-white text-right"
                      : "bg-gray-200 text-black text-left"
                  }`}
                >
                  {m.text === "답변 준비 중입니다..." ? (
                    <LoadingDots />
                  ) : (
                    m.text
                  )}
                </span>
                <span className="ml-1 text-xs text-gray-400">
                  {m.timestamp}
                </span>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* 입력창 + 버튼 */}
        <div className="mt-4 flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault(); // 줄바꿈 막고 보냄
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
