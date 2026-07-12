import { ChatWindow } from "./components/chat/ChatWindow";
import { BackgroundBlobs } from "./components/decor/BackgroundBlobs";
import { Sidebar } from "./components/layout/Sidebar";
import { TopBar } from "./components/layout/TopBar";
import { CsvDropzone } from "./components/upload/CsvDropzone";
import { useSessionStore } from "./store/sessionStore";

export default function App() {
  const sessionId = useSessionStore((s) => s.sessionId);

  return (
    <div className="dot-grid relative flex h-screen flex-col overflow-hidden bg-bg font-sans text-white">
      <BackgroundBlobs />
      <TopBar />
      {sessionId == null ? (
        <CsvDropzone />
      ) : (
        <div className="flex flex-1 overflow-hidden">
          <Sidebar />
          <ChatWindow />
        </div>
      )}
    </div>
  );
}
