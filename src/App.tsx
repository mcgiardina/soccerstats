import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import SeasonPage from "./pages/SeasonPage";
import GamePage from "./pages/GamePage";
import NewGamePage from "./pages/NewGamePage";
import OpponentPage from "./pages/OpponentPage";
import LoginPage from "./pages/LoginPage";
import SettingsPage from "./pages/SettingsPage";
import CoachPage from "./pages/CoachPage";
import { TeamProvider } from "./lib/team";
import ReportPage from "./pages/ReportPage";
import { useAuth } from "./lib/auth";
import { supabaseConfigured } from "./lib/supabase";

function RequireAdmin({ children }: { children: React.ReactElement }) {
  const { isAdmin, ready } = useAuth();
  if (!ready) return null;
  return isAdmin ? children : <Navigate to="/login" replace />;
}

export default function App() {
  const { isAdmin } = useAuth();
  if (!supabaseConfigured) {
    return (
      <div className="page">
        <div className="card">
          <h1>Setup needed</h1>
          <p>Copy <code>.env.example</code> to <code>.env</code> and fill in the Supabase URL, anon key, and admin email. Then restart the dev server.</p>
        </div>
      </div>
    );
  }
  return (
    <TeamProvider isAdmin={isAdmin}>
    <Layout>
      <Routes>
        <Route path="/" element={<SeasonPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/games/new" element={<RequireAdmin><NewGamePage /></RequireAdmin>} />
        <Route path="/games/:id" element={<GamePage />} />
        <Route path="/games/:id/report" element={<ReportPage />} />
        <Route path="/g/:id" element={<GamePage shareView />} />
        <Route path="/g/:id/report" element={<ReportPage />} />
        <Route path="/opponents/:name" element={<OpponentPage />} />
        <Route path="/settings" element={<RequireAdmin><SettingsPage /></RequireAdmin>} />
        <Route path="/coach" element={<CoachPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
    </TeamProvider>
  );
}
