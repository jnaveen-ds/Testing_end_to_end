import { useEffect, useRef, useState } from "react";
import { createAnalysis, getJob, type Job } from "./api";

export default function App() {
  const [text, setText] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const submit = async () => {
    if (!text.trim()) return;
    setError(null);
    try {
      const created = await createAnalysis(text);
      setJob(created);
    } catch (e) {
      setError(String(e));
    }
  };

  // Poll until the worker finishes (or fails) — the classic job-status pattern.
  useEffect(() => {
    if (!job || (job.status === "completed" || job.status === "failed")) return;
    timer.current = window.setInterval(async () => {
      try {
        setJob(await getJob(job.id));
      } catch (e) {
        setError(String(e));
      }
    }, 1500);
    return () => window.clearInterval(timer.current);
  }, [job]);

  return (
    <main className="app">
      <h1>Feedback Analyzer</h1>
      <p className="hint">Submit feedback text — a worker analyzes it with the configured LLM provider.</p>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Paste customer feedback here..."
        rows={6}
      />
      <button onClick={submit} disabled={!text.trim()}>Analyze</button>

      {error && <p className="error">{error}</p>}

      {job && (
        <section className="result">
          <p>
            Job <code>{job.id}</code> —{" "}
            <span className={`status ${job.status}`}>{job.status}</span>
          </p>
          {job.status === "completed" && (
            <>
              <p><b>Summary:</b> {job.summary}</p>
              <p><b>Sentiment:</b> {job.sentiment}</p>
              <p><b>Themes:</b> {job.themes?.join(", ") || "—"}</p>
              <p className="usage">
                Usage: {job.prompt_tokens} prompt + {job.completion_tokens} completion tokens,
                {" "}{job.latency_ms} ms
              </p>
            </>
          )}
          {job.status === "failed" && <p className="error">{job.error}</p>}
        </section>
      )}
    </main>
  );
}
