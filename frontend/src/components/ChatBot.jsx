import axios from "axios";
import LoadingDots from "./LoadingDots";
import React, { useEffect, useState, useRef } from "react";

function ChatBot() {
  /*
    const [aiData, setAiData] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
      const fetchData = () => {
        axios
          .get("https://aismartfarm.duckdns.org/api/ai_diagnosis")
          .then((response) => {
            if (response.data.status == "Send Success!!") {
              setAiData(response.data);
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

      // 이후 5초마다 fetchData 반복 실행
      const interval = setInterval(fetchData, 5000); // 5000ms = 5초

      return () => clearInterval(interval);
    }, []);

    if (!aiData) {
      return <p>데이터 로딩 중...</p>;
    }
      */
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

  const sendMessage = () => {
    if (!input.trim()) return;
    // 사용자 메시지 추가
    setMessages((prev) => [...prev, { sender: "user", text: input }]);
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
      setMessages((prev) => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 1] = {
          sender: "bot",
          text: "봇의 실제 답변 내용",
          timestamp: new Date().toLocaleTimeString("ko-KR", {
            hour: "2-digit",
            minute: "2-digit",
          }),
        };
        return newMessages;
      });
    }, 2000);
  };

  // 채팅창 자동으로 아래로 내리기
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollTop = messagesEndRef.current.scrollHeight;
    }
  }, [messages]);

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
