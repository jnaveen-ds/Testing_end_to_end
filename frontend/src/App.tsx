import { useState } from "react";
import ChatPage from "./pages/ChatPage";
import FeedbackPage from "./pages/FeedbackPage";

export default function App() {
  const [page, setPage] = useState<"chat" | "feedback">("chat");

  return (
    <div className="app-shell">
      <header className="site-header">
        <div>
          <p className="eyebrow">Azure GenAI deployment lab</p>
          <h1>GenAI Learning Studio</h1>
          <p>Small applications for learning production deployment patterns without hiding the fundamentals.</p>
        </div>
      </header>
      <nav className="tabs" aria-label="Learning applications">
        <button className={page === "chat" ? "active" : ""} onClick={() => setPage("chat")}>App 1 · Chat</button>
        <button className={page === "feedback" ? "active" : ""} onClick={() => setPage("feedback")}>Feedback Analyzer</button>
      </nav>
      <main className="app">
        {page === "chat" ? <ChatPage /> : <FeedbackPage />}
      </main>
    </div>
  );
}
