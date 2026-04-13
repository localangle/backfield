import { useEffect, useState } from "react";

const API = import.meta.env.VITE_STYLEBOOK_API_BASE || "http://localhost:8003";

export default function App() {
  const [health, setHealth] = useState<unknown>(null);

  useEffect(() => {
    void fetch(`${API}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ ok: false, error: "fetch failed" }));
  }, []);

  return (
    <div style={{ padding: 24, maxWidth: 640 }}>
      <h1>Stylebook</h1>
      <p style={{ opacity: 0.8 }}>Companion to Agate in Backfield.</p>
      <p>
        <a href="http://localhost:5173" style={{ color: "#1d9bf0" }}>
          Open Agate UI
        </a>
      </p>
      <h2 style={{ fontSize: 16, marginTop: 24 }}>API health</h2>
      <pre style={{ background: "#15202b", padding: 12, borderRadius: 8, overflow: "auto" }}>
        {JSON.stringify(health, null, 2)}
      </pre>
    </div>
  );
}
