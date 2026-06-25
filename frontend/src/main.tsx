import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

// Types
type Role = "employee" | "admin";
type SessionMode = "individual" | "group";
type SessionStatus = "active" | "finished";
type AppView = "monitor" | "history" | "admin";

type User = { id: string; name: string; username: string; role: Role; job_role_id?: string | null; area_id?: string | null; preset_id?: string | null; active: boolean };
type PPE = { code: string; name: string; positive_class: string; negative_class: string };
type Preset = { id: string; name: string; ppe_codes: string[]; active: boolean };
type JobRole = { id: string; name: string; preset_id?: string | null };
type Area = { id: string; name: string; preset_id?: string | null };

type Session = {
  id: string; user_id: string; mode: SessionMode; preset_id?: string | null;
  required_ppe: string[]; status: SessionStatus; started_at: string;
  ended_at?: string | null; machine_locked: boolean;
  tracks: Record<string, TrackSummary>; latency_metrics: LatencyMetric[];
};

type LatencyMetric = { frame_id: string; inference_ms: number; processing_ms: number; server_total_ms: number };

type TrackSummary = {
  track_id: string; user_id?: string | null; samples: number; compliant_samples: number;
  ppe: Record<string, { ppe_code: string; state: string; ratio: number; severity: number }>;
};

type SafetyEvent = {
  id: string; session_id: string; track_id: string; user_id?: string | null;
  ppe_code: string; severity: number; started_at: string; ended_at?: string | null;
  duration_seconds: number;
};

type ComplianceSnapshot = {
  timestamp: string; track_id: string; user_id?: string | null;
  ppe_code: string; state: string; severity: number; ratio: number;
};

type PostureSnapshot = {
  timestamp: string; track_id: string; state: string; severity: number;
  reba_score: number; ergonomic_score: number; confidence: number;
};

type Detection = { class_name: string; confidence: number; box: number[]; track_id?: string | null; ppe_code?: string | null; evidence?: number | null };

type PostureDetection = {
  track_id: string; box: number[]; reba_score: number; ergonomic_score: number;
  state: string; severity: number; confidence: number; posture_mode?: string | null;
  penalties?: Record<string, number>;
};

type FrameResult = {
  frame_id: string; image_width: number; image_height: number; detections: Detection[];
  tracks: Array<{ track_id: string; ppe: Record<string, { state: string; ratio: number; severity: number }>; compliant: boolean }>;
  posture?: PostureDetection[];
  machine_locked: boolean; inference_ms: number; processing_ms: number;
  server_total_ms: number; server_sent_at_ms: number;
};

type Report = {
  session_id: string; duration_seconds: number; required_ppe: string[];
  compliance_percent: number; events_by_severity: Record<string, number>;
  infractions: number; machine_cuts: number; latency: Record<string, number>;
  track_summaries: TrackSummary[]; events?: SafetyEvent[]; timeline?: ComplianceSnapshot[];
  posture_timeline?: PostureSnapshot[];
  session_started_at?: string | null; session_ended_at?: string | null;
};

// Icons
type IP = { size?: number };
const sv = (size: number, children: React.ReactNode) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);
const IcMonitor  = ({ size = 18 }: IP) => sv(size, <><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></>);
const IcHistory  = ({ size = 18 }: IP) => sv(size, <><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></>);
const IcSettings = ({ size = 18 }: IP) => sv(size, <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></>);
const IcLogout   = ({ size = 16 }: IP) => sv(size, <><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></>);
const IcPlay     = ({ size = 16 }: IP) => sv(size, <><polygon points="5 3 19 12 5 21 5 3"/></>);
const IcStop     = ({ size = 14 }: IP) => sv(size, <><rect x="3" y="3" width="18" height="18" rx="2"/></>);
const IcRefresh  = ({ size = 14 }: IP) => sv(size, <><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></>);
const IcDownload = ({ size = 15 }: IP) => sv(size, <><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></>);
const IcCheck    = ({ size = 11 }: IP) => sv(size, <><polyline points="20 6 9 17 4 12"/></>);
const IcBack     = ({ size = 16 }: IP) => sv(size, <><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></>);
const IcLock     = ({ size = 14 }: IP) => sv(size, <><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></>);
const IcUnlock   = ({ size = 14 }: IP) => sv(size, <><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 019.9-1"/></>);
const IcClock    = ({ size = 13 }: IP) => sv(size, <><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></>);
const IcCalendar = ({ size = 13 }: IP) => sv(size, <><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></>);
const IcShield   = ({ size = 16 }: IP) => sv(size, <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></>);
const IcUser     = ({ size = 15 }: IP) => sv(size, <><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></>);

// API
const API_BASE = import.meta.env.VITE_API_URL ?? "";

function wsBase() {
  if (API_BASE) return API_BASE.replace(/^http/, "ws");
  const protocol = location.protocol === "https:" ?"wss" : "ws";
  const backendHost = location.port === "5173" ?`${location.hostname}:8000` : location.host;
  return `${protocol}://${backendHost}`;
}

async function api<T>(path: string, token?: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? "Erro inesperado");
  }
  return response.json();
}

function percentile(values: number[], p: number) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.round((sorted.length - 1) * p))];
}

function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}min ${s}s`;
}

function ppeNameMap(ppe: PPE[]) {
  return Object.fromEntries(ppe.map((item) => [item.code, item.name]));
}

function formatPpeNames(codes: string[], ppe: PPE[]) {
  const names = ppeNameMap(ppe);
  return codes.map((code) => names[code] ?? code).join(", ");
}

function presetForUser(user: User, presets: Preset[]) {
  return presets.find((preset) => preset.id === user.preset_id) ?? null;
}
// App
function App() {
  const [token, setToken] = useState(localStorage.getItem("token") ?? "");
  const [user, setUser] = useState<User | null>(null);
  const [ppe, setPpe] = useState<PPE[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [view, setView] = useState<AppView>("monitor");
  const ignoredSessionIds = useRef(new Set<string>());

  async function bootstrap(nextToken = token) {
    if (!nextToken) return;
    const [me, ppeList, sessionList, presetList] = await Promise.all([
      api<User>("/api/auth/me", nextToken),
      api<PPE[]>("/api/ppe", nextToken),
      api<Session[]>("/api/sessions", nextToken),
      api<Preset[]>("/api/presets", nextToken),
    ]);
    setUser(me);
    setPpe(ppeList);
    setSessions(sessionList);
    setPresets(presetList);
    setActiveSession(sessionList.find((s) => s.status === "active" && !ignoredSessionIds.current.has(s.id)) ?? null);
  }

  useEffect(() => {
    bootstrap().catch(() => { localStorage.removeItem("token"); setToken(""); });
  }, []);

  async function handleLogin(username: string, password: string) {
    setError("");
    const response = await api<{ access_token: string; user: User }>("/api/auth/login", undefined, {
      method: "POST", body: JSON.stringify({ username, password }),
    });
    localStorage.setItem("token", response.access_token);
    setToken(response.access_token);
    setUser(response.user);
    await bootstrap(response.access_token);
  }

  function logout() {
    localStorage.removeItem("token");
    setToken(""); setUser(null); setActiveSession(null); setReport(null);
  }

  async function createSession(mode: SessionMode, additional_ppe: string[]) {
    const session = await api<Session>("/api/sessions", token, {
      method: "POST", body: JSON.stringify({ mode, additional_ppe }),
    });
    setActiveSession(session);
    setReport(null);
    setView("monitor");
    await bootstrap();
  }

  async function endSession() {
    if (!activeSession) return;
    const sessionToEnd = activeSession;
    const sessionId = sessionToEnd.id;
    ignoredSessionIds.current.add(sessionId);
    setActiveSession(null);
    try {
      const generated = await api<Report>(`/api/sessions/${sessionId}/end`, token, {
        method: "POST", body: JSON.stringify({ reason: "Encerrada pelo operador" }),
      });
      setReport(generated);
      await bootstrap();
    } catch (err) {
      ignoredSessionIds.current.delete(sessionId);
      setActiveSession(sessionToEnd);
      throw err;
    }
  }
  async function resetMachine() {
    if (!activeSession) return;
    await api(`/api/sessions/${activeSession.id}/reset-machine`, token, { method: "POST", body: "{}" });
    const refreshed = await api<Session>(`/api/sessions/${activeSession.id}`, token);
    setActiveSession(refreshed);
  }

  if (!token || !user) {
    return <Login onLogin={handleLogin} error={error} setError={setError} />;
  }

  function renderMonitorView() {
    if (activeSession) {
      return (
        <div className="card">
          <Monitor
            token={token} session={activeSession} ppe={ppe}
            onEnd={endSession} onReset={resetMachine} onSessionUpdate={(updated) => {
              if (ignoredSessionIds.current.has(updated.id) || updated.status !== "active") return;
              setActiveSession(updated);
            }}
          />
        </div>
      );
    }
    if (report) {
      return (
        <div className="card">
          <div className="view-nav">
            <button className="btn-back" onClick={() => setReport(null)}>
              <IcBack size={14} /> Nova sessão
            </button>
            <h2>Relatório da sessão</h2>
          </div>
          <ReportView report={report} token={token} />
        </div>
      );
    }
    return (
      <div className="start-grid">
        <div className="card">
          <StartSession user={user!} ppe={ppe} presets={presets} onStart={createSession} />
        </div>
        <aside className="card side-card">
          <h2>Sessões recentes</h2>
          <div className="session-list">
            {sessions.length === 0 ?(
              <div className="empty-state">
                <div className="empty-icon-wrap"><IcHistory size={26} /></div>
                <p>Nenhuma sessão ainda</p>
              </div>
            ) : (
              sessions.slice().reverse().slice(0, 6).map((s) => (
                <div key={s.id} className="session-row">
                  <div className="session-row-top">
                    <span className="session-mode">{s.mode === "individual" ?"Individual" : "Grupo"}</span>
                    <span className={`badge ${s.status === "active" ?"badge-green" : "badge-muted"}`}>
                      {s.status === "active" && <span className="dot dot-green" />}
                      {s.status === "active" ?"Ativa" : "Finalizada"}
                    </span>
                  </div>
                  <div className="session-time">{new Date(s.started_at).toLocaleString("pt-BR")}</div>
                </div>
              ))
            )}
          </div>
          {sessions.length > 6 && (
            <button className="btn-ghost btn-sm" style={{ marginTop: ".75rem", width: "100%" }} onClick={() => setView("history")}>
              Ver histórico completo
            </button>
          )}
        </aside>
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-brand">
          <div className="topbar-logo">
            <img src="/logo.jpg" alt="Code&Ops" />
          </div>
          <div>
            <div className="app-name">EPI Guard</div>
            <div className="app-subtitle">Monitoramento inteligente de EPIs</div>
          </div>
        </div>

        <nav className="topbar-nav">
          <button
            className={`nav-tab ${view === "monitor" ?"active" : ""}`}
            onClick={() => setView("monitor")}
          >
            <IcShield size={15} />
            <span>Monitoramento</span>
            {activeSession && <span className="nav-badge" />}
          </button>
          <button
            className={`nav-tab ${view === "history" ?"active" : ""}`}
            onClick={() => setView("history")}
          >
            <IcHistory size={15} />
            <span>Histórico</span>
          </button>
          {user.role === "admin" && (
            <button
              className={`nav-tab ${view === "admin" ?"active" : ""}`}
              onClick={() => setView("admin")}
            >
              <IcSettings size={15} />
              <span>Administração</span>
            </button>
          )}
        </nav>

        <div className="topbar-right">
          <div className="user-info">
            <div className="user-name">{user.name}</div>
            <div className="user-role">{user.role === "admin" ?"Administrador" : "Funcionário"}</div>
          </div>
          <button className="btn-ghost btn-icon" onClick={logout} title="Sair">
            <IcLogout size={16} />
          </button>
        </div>
      </header>

      {error && (
        <div className="toast">
          <IcShield size={15} />
          {error}
        </div>
      )}

      {view === "monitor" && renderMonitorView()}
      {view === "history" && (
        <div className="card">
          <HistoryView sessions={sessions} token={token} />
        </div>
      )}
      {view === "admin" && user.role === "admin" && (
        <div className="card">
          <AdminPanel token={token} ppe={ppe} />
        </div>
      )}
    </div>
  );
}

// Login
function Login({
  onLogin, error, setError,
}: { onLogin: (u: string, p: string) => Promise<void>; error: string; setError: (e: string) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [loading, setLoading] = useState(false);
  return (
    <div className="login-page">
      <form
        className="login-card"
        onSubmit={async (e) => {
          e.preventDefault();
          setLoading(true);
          try { await onLogin(username, password); }
          catch (err) { setError(err instanceof Error ?err.message : "Falha no login"); }
          finally { setLoading(false); }
        }}
      >
        <div className="login-header">
          <div className="login-logo"><img src="/logo.jpg" alt="Code&Ops" /></div>
          <div>
            <h1>EPI Guard</h1>
            <p className="login-subtitle">Monitoramento inteligente de EPIs</p>
          </div>
        </div>
        {error && <div className="login-error">{error}</div>}
        <div className="login-field">
          <label>Login</label>
          <input value={username} autoComplete="username" onChange={(e) => setUsername(e.target.value)} placeholder="Usuário" />
        </div>
        <div className="login-field">
          <label>Senha</label>
          <input type="password" value={password} autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
        </div>
        <button className="btn-primary" disabled={loading} style={{ width: "100%", marginTop: ".25rem", padding: ".85rem" }}>
          {loading ?"Entrando..." : "Entrar"}
        </button>
        <div className="login-hint">
          Primeira execução: <strong>admin / admin123</strong> ou <strong>funcionario / func123</strong>
        </div>
      </form>
    </div>
  );
}

// StartSession
function StartSession({
  user, ppe, presets, onStart,
}: { user: User; ppe: PPE[]; presets: Preset[]; onStart: (mode: SessionMode, extra: string[]) => Promise<void> }) {
  const [mode, setMode] = useState<SessionMode>("individual");
  const [extra, setExtra] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const linkedPreset = presetForUser(user, presets);
  const employeePpe = linkedPreset?.ppe_codes ?? [];
  const canChoosePpe = user.role === "admin";

  return (
    <div>
      <div className="section-header">
        <h1>Nova sessão de monitoramento</h1>
        {canChoosePpe ?(
          <p className="muted">Como administrador, você pode iniciar uma leitura manual e escolher EPIs adicionais.</p>
        ) : (
          <p className="muted">Os EPIs desta leitura são definidos pelo preset vinculado pelo administrador.</p>
        )}
      </div>

      <div className="form-section-label">Modo de operação</div>
      <div className="mode-toggle">
        <button type="button" className={mode === "individual" ?"active" : ""} onClick={() => setMode("individual")}>
          <IcUser size={15} /> Individual
        </button>
        <button type="button" className={mode === "group" ?"active" : ""} onClick={() => setMode("group")}>
          <IcUser size={15} /> Grupo
        </button>
      </div>

      {!canChoosePpe && (
        <div className="linked-preset-card">
          <div className="linked-preset-label">Preset vinculado</div>
          <div className="linked-preset-name">{linkedPreset?.name ?? "Nenhum preset específico"}</div>
          <div className="linked-preset-ppe">
            {employeePpe.length ?formatPpeNames(employeePpe, ppe) : "Sem preset vinculado; o sistema usará todos os EPIs cadastrados."}
          </div>
        </div>
      )}

      {canChoosePpe && ppe.length > 0 && (
        <>
          <div className="form-section-label">EPIs adicionais/manuais</div>
          <div className="ppe-grid">
            {ppe.map((item) => (
              <label key={item.code} className={`ppe-item ${extra.includes(item.code) ?"checked" : ""}`}>
                <input
                  type="checkbox"
                  checked={extra.includes(item.code)}
                  onChange={(e) =>
                    setExtra((cur) => e.target.checked ?[...cur, item.code] : cur.filter((c) => c !== item.code))
                  }
                />
                <div className="ppe-check">{extra.includes(item.code) && <IcCheck size={10} />}</div>
                {item.name}
              </label>
            ))}
          </div>
        </>
      )}

      <button
        className="btn-primary"
        disabled={loading}
        onClick={async () => { setLoading(true); await onStart(mode, canChoosePpe ?extra : []); setLoading(false); }}
        style={{ marginTop: ".5rem" }}
      >
        <IcPlay size={14} />
        {loading ?"Iniciando..." : "Iniciar monitoramento"}
      </button>
    </div>
  );
}
// Monitor
function Monitor({
  token, session, ppe, onEnd, onReset, onSessionUpdate,
}: { token: string; session: Session; ppe: PPE[]; onEnd: () => Promise<void>; onReset: () => Promise<void>; onSessionUpdate: (s: Session) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const captureRef = useRef<HTMLCanvasElement>(document.createElement("canvas"));
  const wsRef = useRef<WebSocket | null>(null);
  const inFlight = useRef(false);
  const frames = useRef(new Map<string, number>());
  const [result, setResult] = useState<FrameResult | null>(null);
  const [latencies, setLatencies] = useState<number[]>([]);
  const [status, setStatus] = useState("Inicializando câmera...");
  const [ending, setEnding] = useState(false);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const intervalRef = useRef<number | undefined>(undefined);
  const streamRef = useRef<MediaStream | undefined>(undefined);
  const stoppingRef = useRef(false);
  const ppeName = useMemo(() => Object.fromEntries(ppe.map((p) => [p.code, p.name])), [ppe]);

  function stopMonitoring(finalStatus = "Sessão encerrada") {
    stoppingRef.current = true;
    inFlight.current = false;
    if (intervalRef.current) window.clearInterval(intervalRef.current);
    intervalRef.current = undefined;
    wsRef.current?.close(); wsRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = undefined;
    const video = videoRef.current;
    if (video) { video.pause(); video.srcObject = null; }
    const canvas = overlayRef.current;
    canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    setStatus(finalStatus);
  }

  async function handleEndSession() {
    if (ending) return;
    setEnding(true);
    setConfirmEnd(false);
    stopMonitoring("Encerrando sessão...");
    try { await onEnd(); } finally { setEnding(false); }
  }

  useEffect(() => {
    async function start() {
      stoppingRef.current = false;
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false });
      streamRef.current = stream;
      if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play(); }
      const socket = new WebSocket(`${wsBase()}/api/ws/inference?token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(session.id)}`);
      wsRef.current = socket;
      socket.onopen = () => setStatus("Monitorando em tempo real");
      socket.onerror = () => setStatus("Falha no WebSocket");
      socket.onclose = () => { if (!stoppingRef.current) setStatus("WebSocket desconectado"); };
      socket.onmessage = (msg) => {
        if (stoppingRef.current) return;
        inFlight.current = false;
        const parsed = JSON.parse(msg.data);
        if (parsed.error) { setStatus(parsed.error); return; }
        const sent = frames.current.get(parsed.frame_id);
        const e2e = sent ?performance.now() - sent : parsed.server_total_ms;
        frames.current.delete(parsed.frame_id);
        setResult(parsed);
        setStatus(`Monitorando · ${parsed.detections?.length ?? 0} detecções · ${parsed.tracks?.length ?? 0} tracks · ${parsed.posture?.length ?? 0} posturas`);
        setLatencies((items) => [...items.slice(-59), e2e]);
        drawOverlay(parsed);
        if (!stoppingRef.current)
          api<Session>(`/api/sessions/${session.id}`, token).then(onSessionUpdate).catch(() => undefined);
      };
      const interval = window.setInterval(() => {
        const video = videoRef.current;
        if (!video || socket.readyState !== WebSocket.OPEN || inFlight.current || video.videoWidth === 0) return;
        const capture = captureRef.current;
        const scale = 640 / video.videoWidth;
        capture.width = 640; capture.height = Math.round(video.videoHeight * scale);
        capture.getContext("2d")?.drawImage(video, 0, 0, capture.width, capture.height);
        const frameId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        frames.current.set(frameId, performance.now());
        inFlight.current = true;
        socket.send(JSON.stringify({ frame_id: frameId, captured_at_ms: Date.now(), image: capture.toDataURL("image/jpeg", 0.72) }));
      }, 250);
      intervalRef.current = interval;
    }
    function drawOverlay(next: FrameResult) {
      const canvas = overlayRef.current; const video = videoRef.current;
      if (!canvas || !video) return;
      canvas.width = video.clientWidth; canvas.height = video.clientHeight;
      const ctx = canvas.getContext("2d"); if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const sx = canvas.width / next.image_width; const sy = canvas.height / next.image_height;
      next.detections.forEach((det) => {
        const [x1, y1, x2, y2] = det.box;
        const isPerson = det.class_name === "Person";
        ctx.strokeStyle = isPerson ?"#38bdf8" : det.evidence === -1 ?"#ef4444" : "#22c55e";
        ctx.lineWidth = isPerson ?3 : 2;
        const drawX = canvas.width - x2 * sx;
        ctx.strokeRect(drawX, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy);
        ctx.fillStyle = ctx.strokeStyle;
        ctx.font = "13px Inter, sans-serif";
        ctx.fillText(`${det.track_id ?? ""} ${det.class_name} ${(det.confidence * 100).toFixed(0)}%`, drawX + 4, y1 * sy + 16);
      });
      (next.posture ?? []).forEach((posture) => {
        const [x1, y1, x2] = posture.box;
        const drawX = canvas.width - x2 * sx;
        const drawY = Math.max(22, y1 * sy - 8);
        const color = posture.severity >= 2 ?"#ef4444" : posture.severity === 1 ?"#f59e0b" : "#a78bfa";
        const label = `Postura ${posture.track_id}: ${posture.state.toUpperCase()} · REBA ${posture.reba_score.toFixed(0)} · ${posture.ergonomic_score.toFixed(0)}/100`;
        ctx.font = "700 13px Inter, sans-serif";
        const width = ctx.measureText(label).width + 12;
        ctx.fillStyle = "rgba(2, 8, 23, .78)";
        ctx.fillRect(drawX, drawY - 15, width, 20);
        ctx.fillStyle = color;
        ctx.fillText(label, drawX + 6, drawY);
      });
    }
    start().catch((err) => setStatus(err instanceof Error ?err.message : "Falha ao iniciar câmera"));
    return () => { stopMonitoring("Sessão encerrada"); };
  }, [session.id, token]);

  const averageLatency = latencies.length ?latencies.reduce((a, b) => a + b, 0) / latencies.length : 0;
  const isLive = status.startsWith("Monitorando");
  const resetTracks = result?.tracks ?? Object.values(session.tracks ?? {}).map((track) => ({
    track_id: track.track_id,
    ppe: track.ppe,
    compliant: session.required_ppe.every((code) => track.ppe[code]?.state === "present"),
  }));
  const postureByTrack = new Map((result?.posture ?? []).map((item) => [item.track_id, item]));
  const hasResetTracks = resetTracks.length > 0;
  const resetReady = session.machine_locked && hasResetTracks && resetTracks.every((track) =>
    session.required_ppe.every((code) => {
      const item = track.ppe[code];
      return item?.state === "present" || (item?.ratio ?? 0) >= 0.6;
    })
  );
  const resetHint = !hasResetTracks
    ?"Aguardando a câmera reconhecer a pessoa e os EPIs obrigatórios."
    : resetReady
      ?"Todos os EPIs obrigatórios estão conformes. Reset liberado."
      : "Reset bloqueado: todos os EPIs obrigatórios precisam estar visíveis e conformes.";

  return (
    <div>
      {/* Header with controls always visible */}
      <div className="monitor-header">
        <div className="monitor-title">
          <h1>Sessão {session.mode === "individual" ?"individual" : "em grupo"}</h1>
          <div className="monitor-status">
            <span className={`dot ${isLive ?"dot-blue" : "dot-amber"}`} />
            {status}
          </div>
        </div>
        <div className="monitor-controls">
          <div className={`machine-status ${session.machine_locked ?"danger" : "ok"}`}>
            {session.machine_locked ?<IcLock size={13} /> : <IcUnlock size={13} />}
            {session.machine_locked ?"CORTE SIMULADO" : "Máquina liberada"}
          </div>
          {session.machine_locked && (
            <div className="reset-control">
              <button className="btn-sm" onClick={onReset} disabled={!resetReady} title={resetHint}>
                <IcRefresh size={13} /> Resetar
              </button>
              <span className={`reset-hint ${resetReady ?"ok" : "blocked"}`}>{resetHint}</span>
            </div>
          )}
          {!confirmEnd ?(
            <button className="btn-danger btn-sm" onClick={() => setConfirmEnd(true)}>
              <IcStop size={13} /> Encerrar sessão
            </button>
          ) : (
            <div className="confirm-end">
              <span>Encerrar sessão?</span>
              <button className="btn-danger btn-sm" onClick={handleEndSession} disabled={ending}>
                {ending ?"Encerrando..." : "Confirmar"}
              </button>
              <button className="btn-sm" onClick={() => setConfirmEnd(false)}>Cancelar</button>
            </div>
          )}
        </div>
      </div>

      {/* Video */}
      <div className="video-wrap">
        <video ref={videoRef} muted playsInline />
        <canvas ref={overlayRef} />
      </div>

      {/* Metrics */}
      <div className="metrics">
        <div className="metric-card">
          <div className="metric-value">{result?.inference_ms.toFixed(0) ?? 0} ms</div>
          <div className="metric-label">Inferência</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{averageLatency.toFixed(0)} ms</div>
          <div className="metric-label">E2E média</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{percentile(latencies, 0.5).toFixed(0)} ms</div>
          <div className="metric-label">p50</div>
        </div>
        <div className="metric-card">
          <div className="metric-value">{percentile(latencies, 0.95).toFixed(0)} ms</div>
          <div className="metric-label">p95</div>
        </div>
      </div>

      {/* Track Cards */}
      <div className="track-grid">
        {(result?.tracks ?? []).map((track) => {
          const trackBlocked = session.required_ppe.some((code) => {
            const item = track.ppe[code];
            return item && item.state !== "present" && (item.severity ?? 0) >= 3;
          });
          const trackAlert = session.required_ppe.some((code) => {
            const item = track.ppe[code];
            return !item || item.state !== "present";
          });
          const displayCompliant = track.compliant && !trackAlert;
          return (
          <div key={track.track_id} className={`track-card ${displayCompliant ?"ok" : "alert"}`}>
            <div className="track-card-header">
              <span className="track-id">Track {track.track_id}</span>
              <span className={`badge ${displayCompliant ?"badge-green" : "badge-red"}`}>
                <span className={`dot ${displayCompliant ?"dot-green" : "dot-red"}`} />
                {displayCompliant ?"Conforme" : trackBlocked ?"Bloqueado" : "Alerta"}
              </span>
            </div>
            {postureByTrack.get(track.track_id) && (
              <div className={`track-posture ${postureByTrack.get(track.track_id)?.state ?? ""}`}>
                <span>Postura ergonômica</span>
                <strong>
                  {postureByTrack.get(track.track_id)?.state === "apto" ?"Apto" : postureByTrack.get(track.track_id)?.state === "atencao" ?"Atenção" : "Inapto"}
                  {" · REBA "}{postureByTrack.get(track.track_id)?.reba_score.toFixed(0)}
                  {" · "}{postureByTrack.get(track.track_id)?.ergonomic_score.toFixed(0)}/100
                </strong>
              </div>
            )}
            <div className="track-ppe-list">
              {session.required_ppe.map((code) => {
                const item = track.ppe[code];
                const state = item?.state ?? "unknown";
                const severity = item?.severity ?? 0;
                const statusText = state === "present"
                  ?`✓ Nível ${severity}`
                  : trackBlocked && severity >= 3
                    ?"Bloqueio pendente"
                    : `${state === "absent" ?"✕" : "?"} Nível ${severity}`;
                return (
                  <div key={code} className="track-ppe-item">
                    <span className="track-ppe-name">{ppeName[code] ?? code}</span>
                    <span className={`track-ppe-status ${state}`}>
                      {statusText}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
          );
        })}
      </div>
    </div>
  );
}

// HistoryView
function HistoryView({ sessions, token }: { sessions: Session[]; token: string }) {
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function viewReport(sessionId: string) {
    setLoadingId(sessionId);
    setLoadError(null);
    try {
      const report = await api<Report>(`/api/reports/${sessionId}`, token);
      setSelectedReport(report);
    } catch (err) {
      setLoadError(err instanceof Error ?err.message : "Erro ao carregar relatório");
    } finally {
      setLoadingId(null);
    }
  }

  if (selectedReport) {
    return (
      <div>
        <div className="view-nav">
          <button className="btn-back" onClick={() => setSelectedReport(null)}>
            <IcBack size={14} /> Voltar ao histórico
          </button>
          <h2>Relatório da sessão</h2>
        </div>
        <ReportView report={selectedReport} token={token} />
      </div>
    );
  }

  const sorted = sessions.slice().reverse();

  return (
    <div>
      <div className="section-header">
        <h1>Histórico de sessões</h1>
        <p className="muted">{sessions.length} {sessions.length === 1 ?"sessão registrada" : "sessões registradas"} neste sistema.</p>
      </div>

      {loadError && <div className="toast" style={{ marginBottom: "1rem" }}>{loadError}</div>}

      {sessions.length === 0 ?(
        <div className="empty-state" style={{ padding: "4rem 1rem" }}>
          <div className="empty-icon-wrap"><IcHistory size={32} /></div>
          <p>Nenhuma sessão registrada</p>
          <p className="muted" style={{ fontSize: ".82rem", marginTop: ".25rem" }}>
            Inicie uma sessão no painel de monitoramento.
          </p>
        </div>
      ) : (
        <div className="history-list">
          {sorted.map((s) => {
            const duration =
              s.ended_at
                ?(new Date(s.ended_at).getTime() - new Date(s.started_at).getTime()) / 1000
                : null;
            const trackCount = Object.keys(s.tracks ?? {}).length;
            return (
              <div key={s.id} className="history-row">
                <div className="history-info">
                  <div className="history-mode">
                    {s.mode === "individual" ?"Sessão individual" : "Sessão em grupo"}
                  </div>
                  <div className="history-meta">
                    <span className="history-meta-item">
                      <IcCalendar size={12} />
                      {new Date(s.started_at).toLocaleString("pt-BR")}
                    </span>
                    {duration !== null && (
                      <span className="history-meta-item">
                        <IcClock size={12} />
                        {formatDuration(duration)}
                      </span>
                    )}
                    {trackCount > 0 && (
                      <span className="history-meta-item">
                        <IcUser size={12} />
                        {trackCount} {trackCount === 1 ?"pessoa" : "pessoas"}
                      </span>
                    )}
                  </div>
                </div>
                <div className="history-row-right">
                  <span className={`badge ${s.status === "active" ?"badge-green" : "badge-muted"}`}>
                    {s.status === "active" && <span className="dot dot-green" />}
                    {s.status === "active" ?"Ativa" : "Finalizada"}
                  </span>
                  {s.status === "finished" && (
                    <button
                      className="btn-ghost btn-sm"
                      onClick={() => viewReport(s.id)}
                      disabled={loadingId === s.id}
                    >
                      {loadingId === s.id ?"Carregando..." : "Ver relatório"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Charts
function TrackComplianceChart({ report }: { report: Report }) {
  const rows = report.track_summaries.slice(0, 6).map((t) => ({
    label: t.track_id,
    value: t.samples ?(t.compliant_samples / t.samples) * 100 : 0,
  }));
  const data = rows.length ?rows : [{ label: "Sem tracks", value: 0 }];
  return (
    <div className="chart-card wide">
      <div className="chart-header">
        <div className="chart-title">Conformidade por pessoa / track</div>
        <div className="chart-subtitle">Percentual de amostras conformes</div>
      </div>
      <div className="bar-list">
        {data.map((item) => (
          <div className="bar-row" key={item.label}>
            <span>{item.label}</span>
            <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.max(2, item.value)}%` }} /></div>
            <b>{item.value.toFixed(1)}%</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function SeverityChart({ report }: { report: Report }) {
  const data = [1, 2, 3].map((l) => ({ label: `Nível ${l}`, value: report.events_by_severity[String(l)] ?? 0 }));
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="chart-card">
      <div className="chart-header">
        <div className="chart-title">Eventos por severidade</div>
        <div className="chart-subtitle">Alertas, infrações e cortes</div>
      </div>
      <svg viewBox="0 0 320 180" role="img" aria-label="Eventos por severidade">
        {data.map((item, i) => {
          const height = (item.value / max) * 110;
          const x = 44 + i * 92; const y = 136 - height;
          const color = ["#f59e0b", "#fb7185", "#ef4444"][i];
          return (
            <g key={item.label}>
              <rect x={x} y={y} width="48" height={height || 2} rx="10" fill={color} />
              <text x={x + 24} y={y - 8} textAnchor="middle" fill="#edf5ff" fontSize="16" fontWeight="800">{item.value}</text>
              <text x={x + 24} y="160" textAnchor="middle" fill="#7aaecb" fontSize="12">{item.label}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function LatencyChart({ report }: { report: Report }) {
  const data = [
    { label: "Média", value: report.latency.average_ms ?? 0 },
    { label: "p50",   value: report.latency.p50_ms ?? 0 },
    { label: "p95",   value: report.latency.p95_ms ?? 0 },
  ];
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="chart-card">
      <div className="chart-header">
        <div className="chart-title">Latência fim a fim</div>
        <div className="chart-subtitle">Resumo operacional em ms</div>
      </div>
      <div className="latency-bars">
        {data.map((item) => (
          <div key={item.label} className="latency-row">
            <span>{item.label}</span>
            <strong>{item.value.toFixed(0)} ms</strong>
            <div className="latency-track">
              <div className="latency-fill" style={{ width: `${Math.max(4, (item.value / max) * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ComplianceDonut({ report }: { report: Report }) {
  const value = Math.max(0, Math.min(100, report.compliance_percent));
  const circumference = 2 * Math.PI * 42;
  const color = value >= 80 ?"#10b981" : value >= 50 ?"#f59e0b" : "#ef4444";
  return (
    <div className="chart-card donut-card">
      <div className="chart-header">
        <div className="chart-title">Conformidade geral</div>
        <div className="chart-subtitle">Aderência da sessão</div>
      </div>
      <svg viewBox="0 0 120 120" role="img" aria-label="Conformidade geral">
        <circle cx="60" cy="60" r="42" fill="none" stroke="#142030" strokeWidth="14" />
        <circle cx="60" cy="60" r="42" fill="none" stroke={color} strokeWidth="14"
          strokeLinecap="round" transform="rotate(-90 60 60)"
          strokeDasharray={`${circumference}`}
          strokeDashoffset={`${circumference * (1 - value / 100)}`}
        />
        <text x="60" y="57" textAnchor="middle" fill="#edf5ff" fontSize="19" fontWeight="900">{value.toFixed(1)}%</text>
        <text x="60" y="74" textAnchor="middle" fill="#7aaecb" fontSize="10">conforme</text>
      </svg>
    </div>
  );
}


const PPE_LABELS: Record<string, string> = {
  helmet: "Capacete",
  gloves: "Luvas",
  goggles: "\u00d3culos",
};

function statusForSeverity(severity: number, state = "present") {
  if (severity >= 3) return { label: "Corte", className: "danger" };
  if (severity === 2) return { label: "Infra\u00e7\u00e3o", className: "warning" };
  if (severity === 1) return { label: "Alerta", className: "notice" };
  if (state !== "present") return { label: "Ausente", className: "missing" };
  return { label: "Conforme", className: "ok" };
}

function PostureSummaryChart({ report }: { report: Report }) {
  const samples = report.posture_timeline ?? [];
  const tracks = Array.from(new Set(samples.map((item) => item.track_id)));
  if (!samples.length) return null;
  return (
    <div className="chart-card wide">
      <div className="chart-header">
        <div className="chart-title">Postura ergonômica</div>
        <div className="chart-subtitle">Média de REBA e score ergonômico por pessoa/track</div>
      </div>
      <div className="posture-summary-list">
        {tracks.map((trackId) => {
          const items = samples.filter((item) => item.track_id === trackId);
          const avgReba = items.reduce((sum, item) => sum + item.reba_score, 0) / items.length;
          const avgScore = items.reduce((sum, item) => sum + item.ergonomic_score, 0) / items.length;
          const worstSeverity = Math.max(...items.map((item) => item.severity));
          const label = worstSeverity >= 2 ?"Inapto" : worstSeverity === 1 ?"Atenção" : "Apto";
          return (
            <div className={`posture-summary-row severity-${worstSeverity}`} key={trackId}>
              <strong>{trackId}</strong>
              <span>{label}</span>
              <span>REBA médio {avgReba.toFixed(1)}</span>
              <span>Score {avgScore.toFixed(1)}/100</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SessionTimelineChart({ report }: { report: Report }) {
  const snapshots = (report.timeline ?? []).slice().sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  const events = (report.events ?? []).slice().sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at));
  const fallbackStart = snapshots[0]?.timestamp ?? events[0]?.started_at;
  const startMs = report.session_started_at ?Date.parse(report.session_started_at) : fallbackStart ?Date.parse(fallbackStart) : Date.now();
  const endMsFromReport = report.session_ended_at ?Date.parse(report.session_ended_at) : startMs + report.duration_seconds * 1000;
  const endMsFromSnapshots = Math.max(endMsFromReport, ...snapshots.map((item) => Date.parse(item.timestamp)));
  const endMsFromEvents = Math.max(endMsFromReport, ...events.map((event) => Date.parse(event.ended_at ?? report.session_ended_at ?? event.started_at)));
  const endMs = Math.max(startMs + 1000, endMsFromSnapshots, endMsFromEvents);
  const durationMs = endMs - startMs;

  const rowKeys = Array.from(new Set([
    ...report.track_summaries.flatMap((track) => report.required_ppe.map((code) => `${track.track_id}|${code}`)),
    ...snapshots.map((item) => `${item.track_id}|${item.ppe_code}`),
    ...events.map((event) => `${event.track_id}|${event.ppe_code}`),
  ]));

  const rows = rowKeys.map((key) => {
    const [trackId, ppeCode] = key.split("|");
    return {
      key,
      trackId,
      ppeCode,
      snapshots: snapshots.filter((item) => item.track_id === trackId && item.ppe_code === ppeCode),
      events: events.filter((event) => event.track_id === trackId && event.ppe_code === ppeCode),
    };
  });

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => ({
    ratio,
    label: formatDuration((durationMs * ratio) / 1000),
  }));

  function segmentsFromSnapshots(items: ComplianceSnapshot[]) {
    if (!items.length) return [];
    const segments: Array<{ left: number; width: number; severity: number; state: string }> = [];
    let current = items[0];
    let segmentStart = Math.max(startMs, Date.parse(current.timestamp));
    for (let i = 1; i < items.length; i += 1) {
      const item = items[i];
      const changed = item.state !== current.state || item.severity !== current.severity;
      if (changed) {
        const segmentEnd = Math.max(segmentStart + 500, Date.parse(item.timestamp));
        segments.push({
          left: ((segmentStart - startMs) / durationMs) * 100,
          width: ((segmentEnd - segmentStart) / durationMs) * 100,
          severity: current.severity,
          state: current.state,
        });
        current = item;
        segmentStart = Date.parse(item.timestamp);
      }
    }
    const finalEnd = Math.max(segmentStart + 500, endMs);
    segments.push({
      left: ((segmentStart - startMs) / durationMs) * 100,
      width: ((finalEnd - segmentStart) / durationMs) * 100,
      severity: current.severity,
      state: current.state,
    });
    return segments;
  }

  function segmentsFromEvents(rowEvents: SafetyEvent[], trackId: string) {
    const track = report.track_summaries.find((item) => item.track_id === trackId);
    const trackPercent = track?.samples ?(track.compliant_samples / track.samples) * 100 : 100;
    if (!rowEvents.length) {
      return [{ left: 0, width: 100, severity: trackPercent >= 99.5 ?0 : -1, state: trackPercent >= 99.5 ?"present" : "unknown" }];
    }
    const segments: Array<{ left: number; width: number; severity: number; state: string }> = [];
    let cursor = startMs;
    rowEvents.forEach((event) => {
      const eventStart = Math.max(startMs, Date.parse(event.started_at));
      const eventEnd = Math.min(endMs, Date.parse(event.ended_at ?? report.session_ended_at ?? new Date(endMs).toISOString()));
      if (eventStart > cursor) {
        segments.push({ left: ((cursor - startMs) / durationMs) * 100, width: ((eventStart - cursor) / durationMs) * 100, severity: 0, state: "present" });
      }
      segments.push({ left: ((eventStart - startMs) / durationMs) * 100, width: Math.max(0.8, ((Math.max(eventEnd, eventStart + 500) - eventStart) / durationMs) * 100), severity: event.severity, state: "absent" });
      cursor = Math.max(cursor, eventEnd);
    });
    if (cursor < endMs) {
      segments.push({ left: ((cursor - startMs) / durationMs) * 100, width: ((endMs - cursor) / durationMs) * 100, severity: 0, state: "present" });
    }
    return segments;
  }

  return (
    <div className="chart-card wide timeline-card">
      <div className="chart-header timeline-header">
        <div>
          <div className="chart-title">{"Evolu\u00e7\u00e3o temporal da sess\u00e3o"}</div>
          <div className="chart-subtitle">{"Momentos de conformidade, aus\u00eancia, alerta, infra\u00e7\u00e3o, corte e recupera\u00e7\u00e3o por EPI"}</div>
        </div>
        <div className="timeline-legend">
          <span><i className="tl-ok" /> Conforme</span>
          <span><i className="tl-missing" /> Ausente sem alerta</span>
          <span><i className="tl-notice" /> {"N\u00edvel 1"}</span>
          <span><i className="tl-warning" /> {"N\u00edvel 2"}</span>
          <span><i className="tl-danger" /> {"N\u00edvel 3"}</span>
        </div>
      </div>

      {rows.length === 0 ?(
        <div className="timeline-empty">Sem eventos ou tracks suficientes para montar a linha do tempo.</div>
      ) : (
        <div className="timeline-table">
          <div className="timeline-axis">
            <span />
            <div className="timeline-scale">
              {ticks.map((tick) => (
                <span key={tick.ratio} style={{ left: `${tick.ratio * 100}%` }}>{tick.label}</span>
              ))}
            </div>
          </div>

          {rows.map((row) => {
            const segments = row.snapshots.length
              ?segmentsFromSnapshots(row.snapshots)
              : segmentsFromEvents(row.events, row.trackId);

            return (
              <div className="timeline-row" key={row.key}>
                <div className="timeline-row-label">
                  <strong>{row.trackId}</strong>
                  <span>{PPE_LABELS[row.ppeCode] ?? row.ppeCode}</span>
                </div>
                <div className="timeline-line">
                  {segments.map((segment, index) => {
                    const status = statusForSeverity(segment.severity, segment.state);
                    return (
                      <div
                        key={`${row.key}-${index}`}
                        className={`timeline-segment ${status.className}`}
                        style={{ left: `${Math.max(0, segment.left)}%`, width: `${Math.min(100, Math.max(0.8, segment.width))}%` }}
                        title={`${PPE_LABELS[row.ppeCode] ?? row.ppeCode} ? ${status.label}`}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ReportView
function ReportView({ report, token }: { report: Report; token: string }) {
  function downloadPdf() {
    fetch(`${API_BASE}/api/reports/${report.session_id}/pdf`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url; link.download = `relatorio-${report.session_id}.pdf`;
        link.click(); URL.revokeObjectURL(url);
      });
  }
  return (
    <div className="report">
      <div className="report-summary-grid">
        <div className="metric-card">
          <div className="metric-value">{formatDuration(report.duration_seconds)}</div>
          <div className="metric-label">Duração</div>
        </div>
        <div className="metric-card">
          <div className="metric-value" style={{ color: report.compliance_percent >= 80 ?"#34d399" : report.compliance_percent >= 50 ?"#fcd34d" : "#f87171" }}>
            {report.compliance_percent.toFixed(1)}%
          </div>
          <div className="metric-label">Conformidade</div>
        </div>
        <div className="metric-card">
          <div className="metric-value" style={{ color: report.infractions > 0 ?"#fca5a5" : undefined }}>{report.infractions}</div>
          <div className="metric-label">Infrações</div>
        </div>
        <div className="metric-card">
          <div className="metric-value" style={{ color: report.machine_cuts > 0 ?"#f87171" : undefined }}>{report.machine_cuts}</div>
          <div className="metric-label">Cortes simulados</div>
        </div>
      </div>

      <div className="report-charts">
        <ComplianceDonut report={report} />
        <SeverityChart report={report} />
        <LatencyChart report={report} />
        <TrackComplianceChart report={report} />
        <PostureSummaryChart report={report} />
        <SessionTimelineChart report={report} />
      </div>

      <button className="download-btn" onClick={downloadPdf}>
        <IcDownload size={14} /> Baixar relatório em PDF
      </button>
    </div>
  );
}

// AdminPanel
function AdminPanel({ token, ppe }: { token: string; ppe: PPE[] }) {
  const [dashboard, setDashboard] = useState<any>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [jobs, setJobs] = useState<JobRole[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("senha123");
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const [presetName, setPresetName] = useState("");
  const [presetPpe, setPresetPpe] = useState<string[]>([]);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const names = ppeNameMap(ppe);

  async function load() {
    const [dash, u, pr, jr, ar] = await Promise.all([
      api("/api/dashboard", token),
      api<User[]>("/api/users", token),
      api<Preset[]>("/api/presets", token),
      api<JobRole[]>("/api/job-roles", token),
      api<Area[]>("/api/areas", token),
    ]);
    setDashboard(dash); setUsers(u); setPresets(pr); setJobs(jr); setAreas(ar);
  }

  async function createEmployee(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      await api("/api/users", token, {
        method: "POST",
        body: JSON.stringify({
          name,
          username,
          password,
          role: "employee",
          job_role_id: jobs[0]?.id,
          area_id: areas[0]?.id,
          preset_id: selectedPresetId || null,
        }),
      });
      setName(""); setUsername(""); setSelectedPresetId("");
      setMessage({ type: "success", text: "Funcionário cadastrado com sucesso." });
      await load();
    } catch (err) {
      setMessage({ type: "error", text: err instanceof Error ?err.message : "Erro ao cadastrar funcionário." });
    }
  }

  async function createPreset(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      if (!presetName.trim()) throw new Error("Informe o nome do preset.");
      if (!presetPpe.length) throw new Error("Selecione pelo menos um EPI.");
      await api("/api/presets", token, {
        method: "POST",
        body: JSON.stringify({ name: presetName, ppe_codes: presetPpe, active: true }),
      });
      setPresetName(""); setPresetPpe([]);
      setMessage({ type: "success", text: "Preset salvo com sucesso." });
      await load();
    } catch (err) {
      setMessage({ type: "error", text: err instanceof Error ?err.message : "Erro ao salvar preset." });
    }
  }

  async function updateUserPreset(userId: string, presetId: string) {
    setMessage(null);
    try {
      await api(`/api/users/${userId}`, token, {
        method: "PATCH",
        body: JSON.stringify({ preset_id: presetId || null }),
      });
      setMessage({ type: "success", text: "Preset do funcionário atualizado." });
      await load();
    } catch (err) {
      setMessage({ type: "error", text: err instanceof Error ?err.message : "Erro ao vincular preset." });
    }
  }

  useEffect(() => {
    load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div>
      <div className="admin-section-title">Painel administrativo</div>
      {message && <div className={`admin-message ${message.type}`}>{message.text}</div>}

      {dashboard && (
        <div className="metrics">
          <div className="metric-card"><div className="metric-value">{dashboard.users}</div><div className="metric-label">Usuários</div></div>
          <div className="metric-card"><div className="metric-value">{dashboard.active_sessions}</div><div className="metric-label">Sessões ativas</div></div>
          <div className="metric-card"><div className="metric-value" style={{ color: dashboard.infractions > 0 ?"#fca5a5" : undefined }}>{dashboard.infractions}</div><div className="metric-label">Infrações</div></div>
          <div className="metric-card"><div className="metric-value">{dashboard.average_latency_ms} ms</div><div className="metric-label">Latência média</div></div>
        </div>
      )}

      <div className="admin-grid">
        <form className="admin-form" onSubmit={createEmployee}>
          <h3>Cadastrar funcionário</h3>
          <label>Nome completo</label>
          <input placeholder="Ex: João da Silva" value={name} onChange={(e) => setName(e.target.value)} />
          <label>Login</label>
          <input placeholder="Ex: joao.silva" value={username} onChange={(e) => setUsername(e.target.value)} />
          <label>Senha inicial</label>
          <input placeholder="Senha" value={password} onChange={(e) => setPassword(e.target.value)} />
          <label>Preset vinculado</label>
          <select value={selectedPresetId} onChange={(e) => setSelectedPresetId(e.target.value)}>
            <option value="">Sem preset específico</option>
            {presets.filter((preset) => preset.active).map((preset) => (
              <option key={preset.id} value={preset.id}>{preset.name} — {formatPpeNames(preset.ppe_codes, ppe)}</option>
            ))}
          </select>
          <button className="btn-primary" style={{ marginTop: ".25rem" }}>Cadastrar</button>
        </form>

        <form className="admin-form" onSubmit={createPreset}>
          <h3>Novo preset de EPIs</h3>
          <label>Nome do preset</label>
          <input placeholder="Ex: Solda, Construção..." value={presetName} onChange={(e) => setPresetName(e.target.value)} />
          <label>EPIs incluídos</label>
          <div className="admin-ppe-checks">
            {ppe.map((item) => (
              <label key={item.code}>
                <input type="checkbox" checked={presetPpe.includes(item.code)}
                  onChange={(e) => setPresetPpe((cur) => e.target.checked ?[...cur, item.code] : cur.filter((c) => c !== item.code))}
                />
                {item.name}
              </label>
            ))}
          </div>
          <button className="btn-primary" style={{ marginTop: ".25rem" }}>Salvar preset</button>
        </form>
      </div>

      <div className="admin-sub-title">Funcionários cadastrados</div>
      <div className="data-table">
        <table>
          <thead><tr><th>Nome</th><th>Login</th><th>Preset</th><th>Status</th></tr></thead>
          <tbody>
            {users.map((u) => {
              const linked = presets.find((preset) => preset.id === u.preset_id);
              return (
                <tr key={u.id}>
                  <td>{u.name}</td>
                  <td style={{ color: "var(--tx-secondary)" }}>{u.username}</td>
                  <td>
                    <select className="table-select" value={u.preset_id ?? ""} onChange={(e) => updateUserPreset(u.id, e.target.value)} disabled={u.role === "admin"}>
                      <option value="">Sem preset específico</option>
                      {presets.filter((preset) => preset.active).map((preset) => (
                        <option key={preset.id} value={preset.id}>{preset.name}</option>
                      ))}
                    </select>
                    {linked && <div className="table-help">{formatPpeNames(linked.ppe_codes, ppe)}</div>}
                  </td>
                  <td><span className={`badge ${u.active ?"badge-green" : "badge-muted"}`}>{u.active ?"Ativo" : "Inativo"}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="admin-sub-title" style={{ marginTop: "1.5rem" }}>Presets configurados</div>
      <div className="data-table">
        <table>
          <thead><tr><th>Nome</th><th>EPIs</th><th>Status</th></tr></thead>
          <tbody>
            {presets.map((preset) => (
              <tr key={preset.id}>
                <td>{preset.name}</td>
                <td style={{ color: "var(--tx-secondary)" }}>{preset.ppe_codes.map((code) => names[code] ?? code).join(", ")}</td>
                <td><span className={`badge ${preset.active ?"badge-blue" : "badge-muted"}`}>{preset.active ?"Ativo" : "Inativo"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
