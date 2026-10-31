import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import mermaid from "mermaid";
import {
  BrainCircuit, UploadCloud, FileText, ShieldCheck, AlertTriangle,
  CheckCircle2, Cpu, Sparkles, ArrowRight, Layers3, Activity,
  GitBranch, Clock3, ChevronRight, WandSparkles, RefreshCw
} from "lucide-react";
import "./style.css";

mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });

const API = "http://localhost:8000";
const NAV = ["Overview", "Requirements", "Architecture", "Verification", "Change"];

function App() {
  const [health, setHealth] = useState(false);
  const [files, setFiles] = useState([]);
  const [project, setProject] = useState(null);
  const [tab, setTab] = useState("Overview");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [resolutions, setResolutions] = useState({});
  const [change, setChange] = useState("Increase capacity to 100,000 concurrent users.");
  const state = project?.state;

  useEffect(() => {
    fetch(`${API}/api/health`)
      .then(r => r.json())
      .then(x => setHealth(Boolean(x.ollama_connected)))
      .catch(() => setHealth(false));
  }, []);

  useEffect(() => {
    if (!state?.architecture?.diagram) return;
    let active = true;
    mermaid.render(`archintel-${Date.now()}`, state.architecture.diagram)
      .then(({ svg }) => {
        const el = document.getElementById("architecture-diagram");
        if (active && el) el.innerHTML = svg;
      })
      .catch(() => {});
    return () => { active = false; };
  }, [state?.architecture?.diagram]);

  const pending = useMemo(
    () => (state?.conflicts || []).filter(c => c.status === "unresolved" && c.severity === "High"),
    [state?.conflicts]
  );
  const answerValue = value => {
    if (typeof value === "string") return value.trim();
    if (!value || typeof value !== "object") return "";
    return value.selected === "Other" ? String(value.custom || "").trim() : String(value.selected || "").trim();
  };
  const answered = pending.filter(c => answerValue(resolutions[c.id])).length;
  const progress = pending.length ? Math.round(answered / pending.length * 100) : 100;

  async function upload() {
    if (!files.length) return;
    setBusy(true); setError("");
    try {
      const data = new FormData();
      files.forEach(file => data.append("files", file));
      data.append("project_name", "ShopSphere");
      const response = await fetch(`${API}/api/analyze`, { method: "POST", body: data });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Analysis failed");
      setProject(result);
      setResolutions({});
      setTab("Overview");
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function approve() {
    if (!project) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`${API}/api/projects/${project.project_id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved: true,
          resolutions: Object.fromEntries(
            Object.entries(resolutions).map(([id, value]) => [id, answerValue(value)])
          )
        })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Approval failed");
      updateProject(result);
      setTab("Architecture");
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function adapt() {
    if (!project || !change.trim()) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`${API}/api/projects/${project.project_id}/change`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ change_text: change, approved: true })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Change analysis failed");
      updateProject(result);
      setTab("Architecture");
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const setAnswer = (id, value) => setResolutions(old => ({ ...old, [id]: value }));
  function updateProject(result) {
    setProject(previous => {
      if (!previous) return result;
      const previousState = previous.state || {};
      const nextState = result.state || {};
      return {
        ...previous,
        ...result,
        state: {
          ...previousState,
          ...nextState,
          architecture: nextState.architecture ?? previousState.architecture,
          verification: nextState.verification ?? previousState.verification
        }
      };
    });
  }
  const categoryLabel = value => String(value || "clarification").replaceAll("_", " ").replace(/\b\w/g, x => x.toUpperCase());

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><BrainCircuit size={23}/></div><div><b>ArchIntel <span>AI</span></b><small>ARCHITECTURE INTELLIGENCE</small></div></div>
        <div className="workspace-label">WORKSPACE</div>
        <div className="project-chip"><span className="project-dot"/><div><b>{project?.project_name || "New project"}</b><small>{project ? "Analysis workspace" : "No active analysis"}</small></div></div>
        <div className="workspace-label nav-label">WORKFLOW</div>
        <div className="side-nav">
          {NAV.map((item, i) => (
            <button key={item} className={tab === item ? "active" : ""} onClick={() => project && setTab(item)} disabled={!project}>
              <span className="nav-number">0{i + 1}</span>{item}{tab === item && <ChevronRight size={16}/>}
            </button>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="model-status"><span className={`pulse ${health ? "live" : ""}`}/><div><b>{health ? "Local AI connected" : "Fallback mode"}</b><small>{health ? "Ollama runtime online" : "Ollama unavailable"}</small></div></div>
          <div className="sidebar-foot"><ShieldCheck size={14}/> Human-controlled architecture</div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="crumb">TCS AI ENGINEERING HACKATHON <span>/</span> CHALLENGE 02</div>
          <div className="topbar-right"><span className="secure-pill"><span/> LOCAL PROCESSING</span><div className="avatar">AI</div></div>
        </header>

        <div className="page-content">
          <section className="page-heading">
            <div><div className="eyebrow"><Sparkles size={14}/> REQUIREMENTS-TO-ARCHITECTURE AGENT</div><h1>Architecture <span>command center</span></h1><p>Turn fragmented requirements into verified, traceable software architecture.</p></div>
            <div className={`run-state ${project ? "has-project" : ""}`}><span className="state-dot"/>{state?.status || "READY TO ANALYZE"}</div>
          </section>

          {error && <div className="error-banner"><AlertTriangle size={17}/>{error}</div>}

          {!project ? (
            <section className="upload-layout">
              <div className="upload-hero panel">
                <div className="hero-orb"><BrainCircuit size={38}/></div>
                <div className="eyebrow">START A NEW ANALYSIS</div>
                <h2>Give your requirements<br/><span>an architectural brain.</span></h2>
                <p>Upload meeting notes, requirement documents, stakeholder emails or technical specifications. ArchIntel will extract, reason, clarify and design.</p>
                <label className="drop-zone">
                  <input type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.log" onChange={e => setFiles(Array.from(e.target.files || []))}/>
                  <UploadCloud size={28}/><b>Drop files here or <span>browse files</span></b><small>PDF, DOCX, TXT, MD, CSV, LOG · Multiple files supported</small>
                </label>
                {files.length > 0 && <div className="selected-files">{files.map((f, i) => <div key={`${f.name}-${i}`}><FileText size={15}/>{f.name}<span>{(f.size / 1024).toFixed(0)} KB</span></div>)}</div>}
                <button className="primary-btn" onClick={upload} disabled={!files.length || busy}>{busy ? <><RefreshCw className="spin" size={17}/> Analyzing evidence…</> : <>Analyze evidence <ArrowRight size={17}/></>}</button>
              </div>
              <div className="side-info">
                <div className="panel capability"><div className="eyebrow">AGENT CAPABILITIES</div><h3>From evidence to decisions</h3>
                  {[["01","Reason across sources","Extract requirements and identify conflicts."],["02","Plan & recommend","Create components, flows and architecture decisions."],["03","Human control","Resolve ambiguity before architecture approval."],["04","Verify & adapt","Trace requirements and assess change impact."]].map(x=><div className="cap-row" key={x[0]}><span>{x[0]}</span><div><b>{x[1]}</b><small>{x[2]}</small></div></div>)}
                </div>
                <div className="privacy-note"><ShieldCheck size={18}/><div><b>Designed for local-first analysis</b><small>Connects to your local Ollama model through the backend API.</small></div></div>
              </div>
            </section>
          ) : (
            <>
              <section className="metric-grid">
                <Metric icon={<Layers3/>} label="Requirements" value={state?.requirements?.length || 0} tone="violet"/>
                <Metric icon={<AlertTriangle/>} label="Clarifications" value={state?.conflicts?.length || 0} tone="amber"/>
                <Metric icon={<GitBranch/>} label="Traceability" value={state?.verification?.requirement_coverage != null ? `${state.verification.requirement_coverage}%` : "—"} tone="blue"/>
                <Metric icon={<Activity/>} label="Verification" value={state?.verification?.score != null ? `${state.verification.score}%` : "Pending"} tone="green"/>
              </section>

              <nav className="tabbar">{NAV.map(item => <button key={item} className={tab === item ? "selected" : ""} onClick={() => setTab(item)}>{item}{item === "Overview" ? <span className="tab-dot"/> : null}</button>)}</nav>

              {tab === "Overview" && <div className="content-grid">
                <section className="panel"><PanelTitle icon={<GitBranch/>} title="Agent execution plan" subtitle="The workflow used to reason about your evidence"/>{state?.plan?.length ? state.plan.map((x, i) => <div className="plan-row" key={i}><CheckCircle2 size={17}/><span>{x.action}</span><em>{x.status}</em></div>) : <Empty text="Execution plan will appear after analysis."/>}</section>
                <section className="panel"><PanelTitle icon={<AlertTriangle/>} title="Conflicts & ambiguity" subtitle="Potential decisions requiring attention"/>{state?.conflicts?.length ? state.conflicts.map(c => <div className="conflict-row" key={c.id}><div className="row-between"><b>{c.id}</b><span className="mini-tag">{categoryLabel(c.category)}</span></div><p>{c.description}</p><small>{c.severity || "Review"} priority · {c.status || "unresolved"}</small></div>) : <Empty text="No conflicts detected."/>}</section>
              </div>}

              {tab === "Requirements" && <section className="panel"><PanelTitle icon={<FileText/>} title="Consolidated requirements" subtitle="Extracted and classified from uploaded evidence"/>{state?.requirements?.length ? state.requirements.map(r => <div className="requirement-row" key={r.id}><div className="row-between"><b>{r.id}</b><span className={`type-tag ${String(r.type).toLowerCase().includes("non") ? "nfr" : ""}`}>{r.type}</span></div><p>{r.statement}</p><small>{r.source} · Evidence: {r.evidence} · Confidence {Math.round((r.confidence || 0) * 100)}%</small></div>) : <Empty text="No extracted requirements."/>}</section>}

              {tab === "Architecture" && <section className="panel"><PanelTitle icon={<GitBranch/>} title="Architecture proposal" subtitle="Generated from approved requirements and decisions"/><div className="architecture-pattern">{state?.architecture?.pattern || "Architecture is awaiting human approval."}</div><div id="architecture-diagram" className="diagram-area"/>{state?.architecture?.components?.map((c, i) => <div className="requirement-row" key={`${c.name}-${i}`}><b>{c.name}</b><p>{c.responsibility}</p><small>Mapped requirements: {c.requirements?.join(", ") || "—"}</small></div>)}<h3 className="subheading">Architecture decision records</h3>{state?.architecture?.adr?.map(a => <div className="conflict-row" key={a.id}><b>{a.id} · {a.title}</b><p>{a.decision}</p><small>{a.reason}</small></div>)}{state?.architecture?.risks?.map((x, i) => <div className="risk-row" key={i}><AlertTriangle size={15}/>{x}</div>)}</section>}

              {tab === "Verification" && <section className="panel"><PanelTitle icon={<ShieldCheck/>} title="Evidence-based verification" subtitle="Checks and requirement-to-component traceability"/>{state?.verification ? <>{state.verification.checks?.map((c, i) => <div className="verification-row" key={i}><span className={c.passed ? "check-ok" : "check-warn"}>{c.passed ? <CheckCircle2 size={17}/> : <AlertTriangle size={17}/>}</span><div><b>{c.name}</b><small>{c.detail}</small></div></div>)}<h3 className="subheading">Traceability matrix</h3>{state.verification.traceability?.map((t, i) => <div className="trace-row" key={i}><b>{t.requirement_id}</b><ArrowRight size={15}/><span>{t.component}</span><small>{t.source}</small></div>)}</> : <Empty text="Approve the clarification decisions to generate architecture verification."/>}</section>}

              {tab === "Change" && <section className="panel change-panel"><PanelTitle icon={<RefreshCw/>} title="Dynamic change scenario" subtitle="Introduce a new requirement and observe architecture adaptation"/><label className="field-label">NEW REQUIREMENT / CHANGE REQUEST</label><textarea value={change} onChange={e => setChange(e.target.value)} placeholder="Example: Support 100,000 concurrent users during seasonal sales."/><button className="primary-btn" disabled={!state?.architecture || busy || !change.trim()} onClick={adapt}>{busy ? "Processing change…" : <>Approve change & run impact analysis <ArrowRight size={17}/></>}</button>{state?.impact_summary && <div className="impact-box"><b>Impact analysis completed</b><p>{state.impact_summary.change}</p><p>Affected components: {state.impact_summary.affected_components?.join(", ")}</p><p>Verification after change: {state.impact_summary.verification_score}%</p></div>}</section>}

              {pending.length > 0 && <section className="human-review">
                <div className="review-header"><div><div className="eyebrow"><ShieldCheck size={14}/> HUMAN-IN-THE-LOOP GATE</div><h2>Clarification <span>review center</span></h2><p>Review each AI-raised question, edit the proposed decision and approve when ready.</p></div><div className="review-progress"><div className="progress-ring"><b>{progress}%</b></div><small>{answered} OF {pending.length} ANSWERED</small></div></div>
                <div className="progress-track"><div style={{width: `${progress}%`}}/></div>
                <div className="review-meta"><span><Clock3 size={14}/> {pending.length - answered} decisions remaining</span><span><ShieldCheck size={14}/> Human approval required</span></div>
                <div className="question-list">
                  {pending.map((c, i) => <article className="question-card" key={c.id}>
                    <div className="question-top"><div className="question-index">{String(i + 1).padStart(2, "0")}</div><div className="question-heading"><div className="question-tags"><span className="id-tag">{c.id}</span><span className="category-tag">{categoryLabel(c.category)}</span><span className="priority-tag">{c.severity || "Review"} priority</span></div><h3>{c.description}</h3>{c.reason && <p className="question-reason">{c.reason}</p>}</div><span className={`answer-status ${answerValue(resolutions[c.id]) ? "done" : ""}`}>{answerValue(resolutions[c.id]) ? "ANSWERED" : "NEEDS INPUT"}</span></div>
                    {c.evidence?.length > 0 && <div className="evidence-strip"><b>Source evidence</b>{c.evidence.map((e, j) => <span key={j}>{e.source}: {e.value}</span>)}</div>}
                    <div className="answer-area">
                      <label>SELECT THE STAKEHOLDER DECISION</label>
                      <div className="mcq-options">
                        {(c.options?.length ? c.options : ["Yes", "No", "Not sure", "Other"]).map(option => (
                          <label className="mcq-option" key={option}>
                            <input type="radio" name={`answer-${c.id}`} value={option}
                              checked={(typeof resolutions[c.id] === "string" ? resolutions[c.id] : resolutions[c.id]?.selected) === option}
                              onChange={() => setAnswer(c.id, { selected: option, custom: "" })}/>
                            <span>{option}</span>
                          </label>
                        ))}
                      </div>
                      {typeof resolutions[c.id] === "object" && resolutions[c.id]?.selected === "Other" && (
                        <textarea rows={3} value={resolutions[c.id]?.custom || ""}
                          onChange={e => setAnswer(c.id, { selected: "Other", custom: e.target.value })}
                          placeholder="Enter your own answer..."/>
                      )}
                      <div className="answer-foot"><span><WandSparkles size={14}/> Choose an option or enter a custom decision using Other.</span><span>{answerValue(resolutions[c.id]).length} characters</span></div>
                    </div>
                  </article>)}
                </div>
                <div className="approval-footer"><div><b>{answered === pending.length ? "All clarifications answered" : "Architecture generation is gated"}</b><small>{answered === pending.length ? "Your decisions are ready to be submitted." : "Answer every high-priority clarification to continue."}</small></div><button className="primary-btn approve-btn" disabled={busy || answered !== pending.length} onClick={approve}>{busy ? "Generating architecture…" : <>Approve decisions & generate architecture <ArrowRight size={17}/></>}</button></div>
              </section>}

              {pending.length === 0 && !state?.architecture && <section className="panel approval-empty"><ShieldCheck size={24}/><div><b>Human approval</b><small>No unresolved high-priority clarifications. You can proceed to architecture generation.</small></div><button className="primary-btn" disabled={busy} onClick={approve}>Approve & generate architecture <ArrowRight size={17}/></button></section>}
            </>
          )}
          <footer className="page-footer"><span>ARCHINTEL AI <i>·</i> TCS CHALLENGE 02</span><span>Reason with evidence. Design with confidence.</span></footer>
        </div>
      </main>
    </div>
  );
}

function Metric({ icon, label, value, tone }) {
  return <div className="metric-card"><div className={`metric-icon ${tone}`}>{icon}</div><div><small>{label}</small><b>{value}</b></div></div>;
}
function PanelTitle({ icon, title, subtitle }) {
  return <div className="panel-title"><div className="panel-icon">{icon}</div><div><h3>{title}</h3><small>{subtitle}</small></div></div>;
}
function Empty({ text }) { return <div className="empty-state">{text}</div>; }

createRoot(document.getElementById("root")).render(<App/>);
