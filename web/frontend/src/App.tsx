import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { ChatPage } from "./pages/ChatPage";
import { LibraryPage } from "./pages/LibraryPage";
import { PracticePage } from "./pages/PracticePage";
import { ReviewPage } from "./pages/ReviewPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="chat/:sessionId" element={<ChatPage />} />
        <Route path="practice" element={<PracticePage />} />
        <Route path="practice/:practiceSessionId" element={<PracticePage />} />
        <Route path="review" element={<ReviewPage />} />
        <Route path="library" element={<LibraryPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
