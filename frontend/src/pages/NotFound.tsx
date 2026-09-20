import { Link } from "react-router-dom";
import { useTitle } from "../useTitle";

export function NotFound() {
  useTitle("Page not found · AutoPitch");
  return (
    <div className="container narrow">
      <p className="eyebrow">404</p>
      <h1>That page doesn&apos;t exist.</h1>
      <p className="lead">The link may be old, or mistyped.</p>
      <div className="row">
        <Link to="/" className="btn primary">
          Go home
        </Link>
        <Link to="/analyze" className="btn outline">
          Analyze a deck
        </Link>
      </div>
    </div>
  );
}
