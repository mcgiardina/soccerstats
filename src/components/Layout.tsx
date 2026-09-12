import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { CONFIG } from "../config";
import { useAuth } from "../lib/auth";
import { useTeam } from "../lib/team";
import { ThemeToggle } from "../lib/theme";

export default function Layout({ children }: { children: ReactNode }) {
  const { isAdmin, logout } = useAuth();
  const team = useTeam();
  return (
    <>
      <nav className="nav">
        <Link to="/" className={`brand ${team.logo ? "has-logo" : ""}`}>
          {team.logo ? <img className="logo" src={team.logo} alt="" /> : null}
          {CONFIG.appName}
          <small>{team.shortName}</small>
        </Link>
        {team.isCoach && !isAdmin ? <Link to="/coach" className="pill">coach</Link> : null}
        <span className="spacer" />
        <div className="nav-actions">
          <ThemeToggle />
          {isAdmin ? (
            <>
              <Link to="/games/new" className="btn sm primary">+ Game</Link>
              <Link to="/settings" className="btn sm">Settings</Link>
              <button className="btn sm" onClick={() => logout()} title="Signed in as admin">Sign out</button>
            </>
          ) : (
            <Link to="/login" className="btn sm">Admin</Link>
          )}
        </div>
      </nav>
      {children}
    </>
  );
}
