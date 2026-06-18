import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";
import RoleDetail from "./pages/RoleDetail";
import Compare from "./pages/Compare";
import Graph from "./pages/Graph";
import LearningPath from "./pages/LearningPath";
import Chat from "./pages/Chat";
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
  const { pathname } = useLocation();
  if (pathname === "/") return <Landing />;
  return (
    <Layout>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/role/:roleName" element={<RoleDetail />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/graph" element={<Graph />} />
        <Route path="/path" element={<LearningPath />} />
        <Route path="/chat" element={<Chat />} />
      </Routes>
    </Layout>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppRoutes />} />
        <Route path="/*" element={<AppRoutes />} />
      </Routes>
    </BrowserRouter>
  );
}
