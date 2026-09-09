import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { CONFIG } from "../config";
import { useAuth } from "../lib/auth";

export default function Layout({ children }: { children: ReactNode }) {
  const { isAdmin, logout } = useAuth();
  return (
    <>
      <nav className="nav">
        <Link to="/" className="brand">
          {CONFIG.logoUrl ? <img src={CONFIG.logoUrl} alt="" style={{ height: 22, verticalAlign: "middle", marginRight: 8 }} /> : null}
          {CONFIG.appName}
          <small>{CONFIG.teamName}</small>
        </Link>
        <span className="spacer" />
        <div className="nav-actions">
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
