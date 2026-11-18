import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Home from "./pages/Home";
import RoleDetail from "./pages/RoleDetail";
import Graph from "./pages/Graph";
import LearningPath from "./pages/LearningPath";
import Match from "./pages/Match";
import Chat from "./pages/Chat";
import News from "./pages/News";
import "./App.css";

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <Sidebar />
      <main className="main">{children}</main>
    </div>
  );
}

function AppRoutes() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        {/* 旧路径兼容：趋势仪表盘已并入首页 */}
        <Route path="/dashboard" element={<Navigate to="/" replace />} />
        <Route path="/role/:roleName" element={<RoleDetail />} />
        <Route path="/compare" element={<Navigate to="/role" replace />} />
        <Route path="/role" element={<RoleDetail />} />
        <Route path="/graph" element={<Graph />} />
        <Route path="/path" element={<LearningPath />} />
        <Route path="/match" element={<Match />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/news" element={<News />} />
      </Routes>
    </Layout>
  );
}

export default function App() {
  // Support path-based port proxies (e.g. code-server /proxy/<port>/):
  // treat the detected prefix as the router basename.
  const basename = window.location.pathname.match(/^(.+\/proxy\/\d+)/)?.[1] || "/";
  return (
    <BrowserRouter basename={basename}>
      <Routes>
        <Route path="/" element={<AppRoutes />} />
        <Route path="/*" element={<AppRoutes />} />
      </Routes>
    </BrowserRouter>
  );
}
