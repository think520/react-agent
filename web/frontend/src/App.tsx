import { lazy, Suspense, type ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LoadingState } from "./components/common";

const ChatPage = lazy(() => import("./pages/ChatPage").then((module) => ({ default: module.ChatPage })));
const KnowledgeMapPage = lazy(() => import("./pages/KnowledgeMapPage").then((module) => ({ default: module.KnowledgeMapPage })));
const LibraryPage = lazy(() => import("./pages/LibraryPage").then((module) => ({ default: module.LibraryPage })));
const PracticePage = lazy(() => import("./pages/PracticePage").then((module) => ({ default: module.PracticePage })));
const ReviewPage = lazy(() => import("./pages/ReviewPage").then((module) => ({ default: module.ReviewPage })));

function page(element: ReactElement) {
  return <ErrorBoundary>{element}</ErrorBoundary>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <Suspense fallback={<LoadingState label="正在打开页面…" />}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/chat" replace />} />
            <Route path="chat" element={page(<ChatPage />)} />
            <Route path="chat/:sessionId" element={page(<ChatPage />)} />
            <Route path="practice" element={page(<PracticePage />)} />
            <Route path="practice/:practiceSessionId" element={page(<PracticePage />)} />
            <Route path="review" element={page(<ReviewPage />)} />
            <Route path="library" element={page(<LibraryPage />)} />
            <Route path="knowledge-map" element={page(<KnowledgeMapPage />)} />
          </Route>
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
