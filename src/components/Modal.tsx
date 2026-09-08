import { useEffect, type ReactNode } from "react";

export default function Modal({ children, onClose, title }: { children: ReactNode; onClose: () => void; title?: string }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        {title ? <div className="row" style={{ justifyContent: "space-between", marginBottom: ".5rem" }}><h2 style={{ margin: 0 }}>{title}</h2><button className="btn sm" onClick={onClose}>✕</button></div> : null}
        {children}
      </div>
    </div>
  );
}
