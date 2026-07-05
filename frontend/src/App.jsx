import { useEffect, useRef, useState } from "react";

const API = "/api";

export default function App() {
  const [documents, setDocuments] = useState([]);
  const [docId, setDocId] = useState(null);
  const [messages, setMessages] = useState([]); // { role, text, sources }
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [activeSource, setActiveSource] = useState(null); // the highlighted citation
  const scrollRef = useRef(null);

  useEffect(() => {
    loadDocuments();
  }, []);

  // Auto-scroll to the bottom on new text.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  async function loadDocuments() {
    const res = await fetch(`${API}/documents/`);
    const data = await res.json();
    setDocuments(data);
    if (data.length && docId == null) setDocId(data[0].id);
  }

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`${API}/documents/`, { method: "POST", body: form });
      const doc = await res.json();
      if (!res.ok) {
        alert(doc.detail || "Upload failed.");
        return;
      }
      await loadDocuments();
      setDocId(doc.id);
      setMessages([]);
      setActiveSource(null);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  // --- Helpers for updating the last (assistant) message during the stream ---
  function patchLast(patch) {
    setMessages((prev) => {
      const copy = prev.slice();
      const last = copy[copy.length - 1];
      copy[copy.length - 1] = { ...last, ...patch(last) };
      return copy;
    });
  }

  function handleEvent(raw) {
    let event = "";
    let data = "";
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!event || !data) return;
    if (event === "sources") {
      const sources = JSON.parse(data);
      patchLast(() => ({ sources }));
    } else if (event === "token") {
      const { text } = JSON.parse(data);
      patchLast((last) => ({ text: last.text + text }));
    } else if (event === "error") {
      const { detail } = JSON.parse(data);
      patchLast((last) => ({ text: last.text + `\n\n⚠️ ${detail}` }));
    }
  }

  async function send() {
    const question = input.trim();
    if (!question || busy || docId == null) return;
    setInput("");
    setActiveSource(null);
    setMessages((m) => [
      ...m,
      { role: "user", text: question },
      { role: "assistant", text: "", sources: [] },
    ]);
    setBusy(true);
    try {
      const res = await fetch(`${API}/ask/stream/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: docId, question, k: 5 }),
      });
      // A non-streaming error (e.g. 503 when Ollama is down) returns JSON, not SSE.
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        patchLast(() => ({ text: `⚠️ ${err.detail || `Request failed (${res.status}).`}` }));
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      // SSE events are separated by a blank line (\n\n). We buffer until a whole event is assembled.
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop(); // the incomplete remainder waits for the next chunk
        for (const part of parts) handleEvent(part);
      }
    } catch (err) {
      patchLast((last) => ({ text: last.text + `\n\n[error: ${err.message}]` }));
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>Contract Assistant</h1>
        <div className="doc-controls">
          <label>
            Contract:{" "}
            <select
              value={docId ?? ""}
              onChange={(e) => {
                setDocId(Number(e.target.value));
                setMessages([]);
                setActiveSource(null);
              }}
            >
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.original_filename}
                </option>
              ))}
            </select>
          </label>
          <label className="upload-btn">
            {uploading ? "Uploading…" : "＋ Upload"}
            <input type="file" accept=".pdf,.docx" onChange={handleUpload} hidden />
          </label>
        </div>
      </header>

      <div className="body">
        <section className="chat">
          <div className="messages" ref={scrollRef}>
            {messages.length === 0 && (
              <p className="empty">Ask a question about the selected contract…</p>
            )}
            {messages.map((m, i) => (
              <Message key={i} message={m} onCite={setActiveSource} />
            ))}
          </div>
          <div className="composer">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Type a question and press Enter…"
              rows={2}
              disabled={docId == null}
            />
            <button onClick={send} disabled={busy || !input.trim() || docId == null}>
              {busy ? "…" : "Send"}
            </button>
          </div>
        </section>

        <aside className="source-panel">
          {activeSource ? (
            <>
              <h3>Source [{activeSource.ref}]</h3>
              <p className="src-meta">
                chunk #{activeSource.index} · distance {activeSource.distance}
              </p>
              <p className="src-content">{activeSource.content}</p>
            </>
          ) : (
            <p className="empty">Click a citation [n] in an answer to see the passage here.</p>
          )}
        </aside>
      </div>
    </div>
  );
}

function Message({ message, onCite }) {
  const { role, text, sources } = message;
  return (
    <div className={`msg ${role}`}>
      <div className="bubble">
        {role === "assistant" ? (
          text ? (
            <Answer text={text} sources={sources || []} onCite={onCite} />
          ) : (
            <span className="thinking">thinking…</span>
          )
        ) : (
          text
        )}
      </div>
    </div>
  );
}

// Makes [n] clickable — only if it points to a real source. Otherwise leaves it as text
// (so, e.g., a hallucinated [6] leads nowhere).
function Answer({ text, sources, onCite }) {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <span>
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (match) {
          const ref = Number(match[1]);
          const source = sources.find((s) => s.ref === ref);
          if (source) {
            return (
              <button key={i} className="cite" onClick={() => onCite(source)}>
                [{ref}]
              </button>
            );
          }
          return (
            <span key={i} className="cite-dead" title="Citation outside the range of sources">
              [{ref}]
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}
