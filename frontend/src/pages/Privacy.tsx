import { Link } from "react-router-dom";
import { useTitle } from "../useTitle";

export function Privacy() {
  useTitle("Privacy and data · AutoPitch");
  return (
    <div className="container narrow prose">
      <p className="eyebrow">Privacy and data</p>
      <h1>What happens to your deck.</h1>
      <p className="lead">
        A pitch deck is confidential. This page says plainly where its content goes. The operator
        of this instance controls the exact providers, so treat the list below as the default
        setup.
      </p>

      <h2>What is stored</h2>
      <ul className="serif plain-list">
        <li>
          <strong>Your PDF is not stored.</strong> It is read in memory to extract slide text and
          then discarded.
        </li>
        <li>
          <strong>The finished report is stored</strong> on the server: the extracted facts, the
          scores, the reasoning and the objections. It is kept for 30 days by default, then
          deleted. You can delete it earlier from <Link to="/reports">My reports</Link>.
        </li>
        <li>
          <strong>There are no accounts.</strong> Reports are tied to a random ID kept in your
          browser&apos;s local storage. Anyone with that browser can see them; clearing the
          browser&apos;s data removes your access to them.
        </li>
      </ul>

      <h2>Who else sees the text</h2>
      <ul className="serif plain-list">
        <li>
          <strong>Language model providers.</strong> The text of your slides, and the extracted
          record, are sent to the configured model providers (by default Groq, and Google Gemini
          if enabled) to extract and score the deck.
        </li>
        <li>
          <strong>Embedding provider.</strong> Only a short description of the company, its sector,
          stage, raise and headline revenue is sent to find comparable funding rounds, not the
          deck text.
        </li>
        <li>
          <strong>OCR provider.</strong> Only when a deck has pages with no selectable text (scans
          or exported images), those pages are sent as a PDF to Mistral OCR to read the text.
          Decks whose text can be read directly are never sent there.
        </li>
        <li>
          <strong>Tracing.</strong> If the operator turns on LangSmith tracing, prompts and model
          responses, which include deck content, are sent to LangSmith for debugging.
        </li>
      </ul>

      <h2>What is not done</h2>
      <ul className="serif plain-list">
        <li>No advertising or analytics trackers on this site.</li>
        <li>Reports are never shown to other visitors.</li>
      </ul>

      <p className="muted">
        Do not upload a deck you are not allowed to share with third-party model providers.
      </p>
    </div>
  );
}
