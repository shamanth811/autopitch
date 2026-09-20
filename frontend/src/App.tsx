import { useEffect } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Analyze } from "./pages/Analyze";
import { Landing } from "./pages/Landing";
import { Methodology } from "./pages/Methodology";
import { NotFound } from "./pages/NotFound";
import { Privacy } from "./pages/Privacy";
import { ReportPage } from "./pages/ReportPage";
import { Reports } from "./pages/Reports";

const NAV = [
  { to: "/analyze", label: "Analyze" },
  { to: "/reports", label: "My reports" },
  { to: "/methodology", label: "Methodology" },
  { to: "/privacy", label: "Privacy" },
];

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export function App() {
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="masthead noprint">
        <nav className="masthead-inner" aria-label="Main">
          <Link to="/" className="wordmark">
            AutoPitch
          </Link>
          <ul className="nav">
            {NAV.map((n) => (
              <li key={n.to}>
                <NavLink to={n.to} className={({ isActive }) => (isActive ? "active" : "")}>
                  {n.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <Link to="/analyze" className="btn primary small">
            Analyze a deck
          </Link>
        </nav>
      </header>

      <ScrollToTop />
      <main id="main">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/reports/:id" element={<ReportPage />} />
          <Route path="/methodology" element={<Methodology />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>

      <footer className="footer noprint">
        <div className="footer-grid">
          <div>
            <p className="footer-mark">AutoPitch</p>
            <p>Deck analysis for founders, grounded in a public rubric.</p>
          </div>
          <div>
            <p className="eyebrow">Product</p>
            <ul>
              <li>
                <Link to="/analyze">Analyze a deck</Link>
              </li>
              <li>
                <Link to="/reports">My reports</Link>
              </li>
            </ul>
          </div>
          <div>
            <p className="eyebrow">About</p>
            <ul>
              <li>
                <Link to="/methodology">Methodology</Link>
              </li>
              <li>
                <Link to="/privacy">Privacy and data</Link>
              </li>
            </ul>
          </div>
        </div>
        <p className="footer-fine">
          Scores are model-generated screening aids from the text of the uploaded deck. They are
          not investment advice.
        </p>
      </footer>
    </>
  );
}
