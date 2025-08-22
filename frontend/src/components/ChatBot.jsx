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

  useEffect(() => {
    const fetchData = () => {
      axios
        .get("https://aivpp.duckdns.org/api/serv_fr/generate_bid")
        //.get("/api/serv_fr/generate_bid")
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
        //.get("/api/serv_fr/bidding_result")
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
    // --- 한국시간 기반 next tick 계산 ---
    const now = new Date();
    const kstNow = new Date(
      now.toLocaleString("en-US", { timeZone: "Asia/Seoul" })
    );

    const minutes = kstNow.getMinutes();
    const seconds = kstNow.getSeconds();

    // 다음 15분 단위 구하기 (0, 15, 30, 45)
    const nextQuarter = Math.ceil(minutes / 15) * 15;
    const waitMinutes = (nextQuarter - minutes + 60) % 60;

    // "정각 + 1분" 타겟 시점까지 남은 시간(ms)
    const waitMs = (waitMinutes * 60 + (60 - seconds)) * 1000;

    // 페이지 로드시 최초 1회 데이터 가져오기
    fetchData();

    // waitMs 후 실행 -> 이후 15분마다 반복
    const timeout = setTimeout(() => {
      fetchData();
      const interval = setInterval(fetchData, 15 * 60 * 1000); // 15분마다 실행
      timeoutTimerRef.current = interval;
    }, waitMs);

    return () => {
      clearTimeout(timeout);
      clearInterval(timeoutTimerRef.current);
    };
  }, []);

  // bid_edit_fix 호출 함수
  const sendBidEditFix = async (action, bids = null) => {
    try {
      const response = await axios.put(
        "https://aivpp.duckdns.org/api/fr_serv/bid_edit_fix",
        //"/api/fr_serv/bid_edit_fix",
        {
          action,
          bids,
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
    const normalizedInput = userInput.replace(/[\s;,]+/g, ""); // 공백제거

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
        if (awaitingEditInputRef.current) {
          // === 2단계: 사용자가 수정입력한 경우 ===
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
              .filter((b) => b !== null); // 매칭 실패한 항목 제거

            if (editBids.length === 0) {
              awaitingEditInputRef.current = false;
              setMessages((prev) => [
                ...prev.slice(0, -1),
                {
                  sender: "bot",
                  text: "입력한 항목에 해당하는 입찰 정보가 없습니다.",
                  timestamp: new Date().toLocaleTimeString("ko-KR", {
                    hour: "2-digit",
                    minute: "2-digit",
                  }),
                },
              ]);
              return;
            }

            const edit_result = await sendBidEditFix("edit", editBids);

            // 상태 종료
            awaitingEditInputRef.current = false;

            const successText = editBids
              .map((b) => `[${b.entity_name}] → ${b.bid_price_per_kwh}원/kWh`)
              .join("\n");

            setMessages((prev) => [
              ...prev.slice(0, -1),
              {
                sender: "bot",
                text:
                  edit_result.status === "success"
                    ? `입찰가 수정 완료:\n${successText}\n\n입찰이 완료되었습니다.`
                    : `수정 실패: ${edit_result.fail_reason}`,
                timestamp: new Date().toLocaleTimeString("ko-KR", {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              },
            ]);
          } else {
            awaitingEditInputRef.current = false;
            setMessages((prev) => [
              ...prev.slice(0, -1),
              {
                sender: "bot",
                text: "형식이 잘못되었습니다. 예: '태양광 130'",
                timestamp: new Date().toLocaleTimeString("ko-KR", {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              },
            ]);
          }
          return; // 2단계 입력은 여기서 종료
        }
        // 수정 없이 진행 입력시
        if (normalizedInput == "수정없이진행") {
          if (!isBiddingActive) {
            // 이미 입찰 종료된 상태라면 메시지 전송
            setMessages((prev) => {
              const newMessages = [...prev];
              newMessages[newMessages.length - 1] = {
                sender: "bot",
                text: "입찰이 이미 종료되었습니다. \n다음 입찰 추천을 기다려주세요.",
                timestamp: new Date().toLocaleTimeString("ko-KR", {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              };
              return newMessages;
            });
            return;
          }
          // 이전 타이머 제거
          if (timeoutTimerRef.current) clearTimeout(timeoutTimerRef.current);
          setIsBiddingActive(false);

          const result = await sendBidEditFix("confirm");

          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = {
              sender: "bot",
              text:
                result.status === "success"
                  ? "입찰이 완료되었습니다."
                  : `오류: ${result.fail_reason}`,
              timestamp: new Date().toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
            };
            return newMessages;
          });
        }
        // === 수정하고진행 (1단계) ===
        else if (normalizedInput == "수정하고진행") {
          if (!isBiddingActive) {
            setMessages((prev) => {
              const newMessages = [...prev];
              newMessages[newMessages.length - 1] = {
                sender: "bot",
                text: "입찰이 이미 종료되었습니다. \n다음 입찰 추천을 기다려주세요.",
                timestamp: new Date().toLocaleTimeString("ko-KR", {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              };
              return newMessages;
            });
            return;
          }
          // 이전 타이머 제거
          if (timeoutTimerRef.current) clearTimeout(timeoutTimerRef.current);

          awaitingEditInputRef.current = true;
          setIsBiddingActive(false);

          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = {
              sender: "bot",
              text: "수정할 항목을 입력해주세요.\n예: 태양광 130, 풍력 40, 배터리 0\n(입찰 거부시 0으로 표시)",
              timestamp: new Date().toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
            };
            return newMessages;
          });
        }
        // 아무거나 입력했을시 출력
        else {
          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = {
              sender: "bot",
              text: "올바른 명령어를 입력해주세요.\n(수정 없이 진행 / 수정하고 진행)",
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
    const checkTimeAndSend = async () => {
      const now = new Date();
      const minutes = now.getMinutes();

      // 00, 15, 30, 45분만, 중복 방지
      if (
        [0, 15, 30, 45].includes(minutes) &&
        lastMinuteRef.current !== minutes &&
        bidData
      ) {
        lastMinuteRef.current = minutes;

        await LatestBidResultMessage(setMessages);

        // 입찰 시작 표시
        setIsBiddingActive(true);

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
            }kWh\n- 입찰가 : ${b.bid_price_per_kwh}원/kWh\n${b.llm_reasoning}`;
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
        // 5분 후 타임아웃 전송
        timeoutTimerRef.current = setTimeout(async () => {
          const result = await sendBidEditFix("timeout");

          setMessages((prev) => [
            ...prev,
            {
              sender: "bot",
              text:
                result.status === "success"
                  ? "응답이 없어 추천된 입찰을 모두 거부하였습니다."
                  : `타임아웃 처리 실패: ${result.fail_reason}, ${result.action}`,
              timestamp: new Date().toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              }),
            },
          ]);
          // 입찰 종료 표시
          setIsBiddingActive(false);
        }, 300000); // 5분 후 타임아웃
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
