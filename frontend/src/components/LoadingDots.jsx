// 답변 대기 애니메이션용 컴포넌트
export default function LoadingDots() {
  return (
    <span className="inline-flex space-x-2">
      <span className="animate-pulse font-bold text-blue-600">.</span>
      <span className="animate-pulse animation-delay-150 font-bold text-blue-600">
        .
      </span>
      <span className="animate-pulse animation-delay-300 font-bold text-blue-600">
        .
      </span>
    </span>
  );
}
