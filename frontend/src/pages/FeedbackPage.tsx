import { useEffect, useRef, useState } from "react";
import { createAnalysis, getJob, type Job } from "../api";

export default function FeedbackPage() {
  const [text, setText] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const submit = async () => {
    if (!text.trim()) return;
    setError(null);
    try {
      setJob(await createAnalysis(text));
    } catch (caught) {
      setError(String(caught));
    }
  };

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;
    timer.current = window.setInterval(async () => {
      try {
        setJob(await getJob(job.id));
      } catch (caught) {
        setError(String(caught));
      }
    }, 1500);
    return () => window.clearInterval(timer.current);
  }, [job]);

  return (
    <section className="workspace" aria-labelledby="feedback-title">
      <div className="section-heading">
        <p className="eyebrow">Existing asynchronous flow</p>
        <h2 id="feedback-title">Feedback Analyzer</h2>
        <p>Submit feedback. A queued worker analyzes it and the page polls for completion.</p>
      </div>

      <label htmlFor="feedback">Customer feedback</label>
      <textarea
        id="feedback"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Paste customer feedback here..."
        rows={6}
      />
      <button type="button" onClick={submit} disabled={!text.trim()}>Analyze</button>

      {error && <p className="error" role="alert">{error}</p>}
      {job && (
        <section className="result" aria-live="polite">
          <p>Job <code>{job.id}</code> — <span className={`status ${job.status}`}>{job.status}</span></p>
          {job.status === "completed" && (
            <>
              <p><b>Summary:</b> {job.summary}</p>
              <p><b>Sentiment:</b> {job.sentiment}</p>
              <p><b>Themes:</b> {job.themes?.join(", ") || "—"}</p>
              <p className="usage">Usage: {job.prompt_tokens} prompt + {job.completion_tokens} completion tokens, {job.latency_ms} ms</p>
            </>
          )}
          {job.status === "failed" && <p className="error">{job.error}</p>}
        </section>
      )}
    </section>
  );
}
