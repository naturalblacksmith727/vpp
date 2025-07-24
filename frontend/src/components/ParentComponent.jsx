import ChatBot from "./ChatBot";
import Graphs from "./Graphs";
import RevenueDashboard from "./RevenueDashboard";

function ParentComponent() {
  return (
    <div>
      <header className="fixed top-0 left-0 w-full bg-white shadow-md h-12 flex items-center px-9">
        <h1 className="text-xl font-bold cursor-pointer">
          가상 발전소(VPP) AI 대화형 전략 어시스턴트
        </h1>
      </header>
      <div className="pt-12 pr-32 relative">
        <RevenueDashboard />
        <div className="mb-12 ml-6">
          <ChatBot />
        </div>
        <Graphs />
      </div>
    </div>
  );
}
export default ParentComponent;
