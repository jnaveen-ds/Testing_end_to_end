import { type FormEvent, useState } from "react";
import { sendChat, type ChatResponse } from "../api";

const MAX_PROMPT_LENGTH = 2000;

export default function ChatPage() {
  const [prompt, setPrompt] = useState("");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!prompt.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      setResponse(await sendChat(prompt.trim()));
    } catch (caught) {
      setError(String(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="workspace" aria-labelledby="chat-title">
      <div className="section-heading">
        <p className="eyebrow">App 1 · Synchronous inference</p>
        <h2 id="chat-title">Real-time Chat</h2>
        <p>Ask a short question. Repeat the exact prompt to observe a cache MISS become a token-free HIT.</p>
      </div>

      <form onSubmit={submit}>
        <label htmlFor="chat-prompt">Your question</label>
        <textarea
          id="chat-prompt"
          value={prompt}
          maxLength={MAX_PROMPT_LENGTH}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="For example: Explain scale to zero in simple words."
          rows={6}
        />
        <div className="form-footer">
          <span className="character-count">{prompt.length}/{MAX_PROMPT_LENGTH}</span>
          <button type="submit" disabled={!prompt.trim() || submitting}>
            {submitting ? "Thinking…" : "Send question"}
          </button>
        </div>
      </form>

      {error && <p className="error" role="alert">{error}</p>}
      {response && (
        <section className="result chat-result" aria-live="polite">
          <div className="result-heading">
            <h3>Assistant response</h3>
            <span className={`cache-badge ${response.cache_status.toLowerCase()}`}>
              Cache {response.cache_status}
            </span>
          </div>
          <p className="answer">{response.answer}</p>
          <dl className="metrics">
            <div><dt>Prompt tokens</dt><dd>{response.prompt_tokens}</dd></div>
            <div><dt>Completion tokens</dt><dd>{response.completion_tokens}</dd></div>
            <div><dt>Model latency</dt><dd>{response.model_latency_ms} ms</dd></div>
            <div><dt>Total latency</dt><dd>{response.total_latency_ms} ms</dd></div>
          </dl>
          <p className="correlation">Correlation ID: <code>{response.correlation_id}</code></p>
        </section>
      )}
    </section>
  );
}
