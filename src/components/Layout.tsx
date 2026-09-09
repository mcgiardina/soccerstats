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
        {isAdmin ? (
          <>
            <span className="pill">admin</span>
            <Link to="/games/new" className="navlink primary">+ Game</Link>
            <a href="#" className="navlink quiet" onClick={(e) => { e.preventDefault(); logout(); }}>Sign out</a>
          </>
        ) : (
          <Link to="/login" className="navlink quiet">Admin</Link>
        )}
      </nav>
      {children}
    </>
  );
}
