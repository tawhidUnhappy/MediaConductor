import { useStore, stopJob } from "../store";
import Terminal from "../components/Terminal";

export default function TerminalTab() {
  const { jobInfo } = useStore();

  return (
    <>
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "6px 12px", background: "var(--bg2)",
        borderBottom: "1px solid var(--border)", flexShrink: 0,
      }}>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>Terminal output</span>
        {jobInfo && (
          <>
            <span style={{ fontSize: 12, color: "var(--blue)" }}>
              ● {jobInfo.name}
            </span>
            <button
              className="btn-danger"
              style={{ marginLeft: "auto", fontSize: 11, padding: "2px 10px" }}
              onClick={stopJob}
            >
              Stop
            </button>
          </>
        )}
      </div>
      <div className="term-wrap" style={{ flex: 1, overflow: "hidden" }}>
        <Terminal />
      </div>
    </>
  );
}
