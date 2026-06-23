import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Role = "employee" | "admin";
type SessionMode = "individual" | "group";
type SessionStatus = "active" | "finished";

type User = {
  id: string;
  name: string;
  username: string;
  role: Role;
  job_role_id?: string | null;
  area_id?: string | null;
  active: boolean;
};

type PPE = {
  code: string;
  name: string;
  positive_class: string;
  negative_class: string;
};

type Preset = {
  id: string;
  name: string;
  ppe_codes: string[];
  active: boolean;
};

type JobRole = { id: string; name: string; preset_id?: string | null };
type Area = { id: string; name: string; preset_id?: string | null };

type Session = {
  id: string;
  user_id: string;
  mode: SessionMode;
  preset_id?: string | null;
  required_ppe: string[];
  status: SessionStatus;
  started_at: string;
  ended_at?: string | null;
  machine_locked: boolean;
  tracks: Record<string, TrackSummary>;
  latency_metrics: LatencyMetric[];
};

type LatencyMetric = {
  frame_id: string;
  inference_ms: number;
  processing_ms: number;
  server_total_ms: number;
};

type TrackSummary = {
  track_id: string;
  user_id?: string | null;
  samples: number;
  compliant_samples: number;
  ppe: Record<string, { ppe_code: string; state: string; ratio: number; severity: number }>;
};

type Detection = {
  class_name: string;
  confidence: number;
  box: number[];
  track_id?: string | null;
  ppe_code?: string | null;
  evidence?: number | null;
};

type FrameResult = {
  frame_id: string;
  image_width: number;
  image_height: number;
  detections: Detection[];
  tracks: Array<{ track_id: string; ppe: Record<string, { state: string; ratio: number; severity: number }>; compliant: boolean }>;
  machine_locked: boolean;
  inference_ms: number;
  processing_ms: number;
  server_total_ms: number;
  server_sent_at_ms: number;
};

type Report = {
  session_id: string;
  duration_seconds: number;
  required_ppe: string[];
  compliance_percent: number;
  events_by_severity: Record<string, number>;
  infractions: number;
  machine_cuts: number;
  latency: Record<string, number>;
  track_summaries: TrackSummary[];
};

const API_BASE = import.meta.env.VITE_API_URL ?? "";

function wsBase() {
  if (API_BASE) return API_BASE.replace(/^http/, "ws");
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const backendHost = location.port === "5173" ? `${location.hostname}:8000` : location.host;
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

function App() {
  const [token, setToken] = useState(localStorage.getItem("token") ?? "");
  const [user, setUser] = useState<User | null>(null);
  const [ppe, setPpe] = useState<PPE[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");

  async function bootstrap(nextToken = token) {
    if (!nextToken) return;
    const [me, ppeList, sessionList] = await Promise.all([
      api<User>("/api/auth/me", nextToken),
      api<PPE[]>("/api/ppe", nextToken),
      api<Session[]>("/api/sessions", nextToken),
    ]);
    setUser(me);
    setPpe(ppeList);
    setSessions(sessionList);
    setActiveSession(sessionList.find((item) => item.status === "active") ?? null);
  }

  useEffect(() => {
    bootstrap().catch(() => {
      localStorage.removeItem("token");
      setToken("");
    });
  }, []);

  async function handleLogin(username: string, password: string) {
    setError("");
    const response = await api<{ access_token: string; user: User }>("/api/auth/login", undefined, {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    localStorage.setItem("token", response.access_token);
    setToken(response.access_token);
    setUser(response.user);
    await bootstrap(response.access_token);
  }

  function logout() {
    localStorage.removeItem("token");
    setToken("");
    setUser(null);
    setActiveSession(null);
    setReport(null);
  }

  async function createSession(mode: SessionMode, additional_ppe: string[]) {
    const session = await api<Session>("/api/sessions", token, {
      method: "POST",
      body: JSON.stringify({ mode, additional_ppe }),
    });
    setActiveSession(session);
    setReport(null);
    await bootstrap();
  }

  async function endSession() {
    if (!activeSession) return;
    const generated = await api<Report>(`/api/sessions/${activeSession.id}/end`, token, {
      method: "POST",
      body: JSON.stringify({ reason: "Encerrada pelo operador" }),
    });
    setReport(generated);
    setActiveSession(null);
    await bootstrap();
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

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <strong>EPI Guard</strong>
          <span>Monitoramento local de EPIs</span>
        </div>
        <div className="user-pill">
          {user.name} · {user.role === "admin" ? "Admin" : "Funcionário"}
          <button onClick={logout}>Sair</button>
        </div>
      </header>

      {error && <div className="toast">{error}</div>}

      <main className="grid">
        <section className="card main-card">
          {!activeSession ? (
            <StartSession ppe={ppe} onStart={createSession} report={report} token={token} />
          ) : (
            <Monitor
              token={token}
              session={activeSession}
              ppe={ppe}
              onEnd={endSession}
              onReset={resetMachine}
              onSessionUpdate={setActiveSession}
            />
          )}
        </section>

        <aside className="card side-card">
          <h2>Histórico</h2>
          <div className="session-list">
            {sessions.slice().reverse().map((session) => (
              <div key={session.id} className="session-row">
                <span>{session.mode === "individual" ? "Individual" : "Grupo"}</span>
                <strong>{session.status === "active" ? "Ativa" : "Finalizada"}</strong>
                <small>{new Date(session.started_at).toLocaleString()}</small>
              </div>
            ))}
          </div>
        </aside>

        {user.role === "admin" && (
          <section className="card admin-card">
            <AdminPanel token={token} ppe={ppe} />
          </section>
        )}
      </main>
    </div>
  );
}

function Login({ onLogin, error, setError }: { onLogin: (u: string, p: string) => Promise<void>; error: string; setError: (e: string) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [loading, setLoading] = useState(false);
  return (
    <div className="login-page">
      <form
        className="login-card"
        onSubmit={async (event) => {
          event.preventDefault();
          setLoading(true);
          try {
            await onLogin(username, password);
          } catch (err) {
            setError(err instanceof Error ? err.message : "Falha no login");
          } finally {
            setLoading(false);
          }
        }}
      >
        <div className="logo">EPI</div>
        <h1>Entrar no EPI Guard</h1>
        <p>Use `admin/admin123` ou `funcionario/func123` para a primeira execução local.</p>
        <label>
          Login
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          Senha
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error && <div className="error">{error}</div>}
        <button disabled={loading}>{loading ? "Entrando..." : "Entrar"}</button>
      </form>
    </div>
  );
}

function StartSession({ ppe, onStart, report, token }: { ppe: PPE[]; onStart: (mode: SessionMode, extra: string[]) => Promise<void>; report: Report | null; token: string }) {
  const [mode, setMode] = useState<SessionMode>("individual");
  const [extra, setExtra] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  return (
    <div>
      <h1>Nova sessão</h1>
      <p className="muted">O preset automático vem da área/função do funcionário. Aqui você pode adicionar EPIs extras à sessão.</p>
      <div className="mode-toggle">
        <button className={mode === "individual" ? "active" : ""} onClick={() => setMode("individual")}>Individual</button>
        <button className={mode === "group" ? "active" : ""} onClick={() => setMode("group")}>Grupo</button>
      </div>
      <div className="checks">
        {ppe.map((item) => (
          <label key={item.code}>
            <input
              type="checkbox"
              checked={extra.includes(item.code)}
              onChange={(event) => setExtra((current) => event.target.checked ? [...current, item.code] : current.filter((code) => code !== item.code))}
            />
            {item.name}
          </label>
        ))}
      </div>
      <button
        className="primary"
        disabled={loading}
        onClick={async () => {
          setLoading(true);
          await onStart(mode, extra);
          setLoading(false);
        }}
      >
        Iniciar monitoramento
      </button>
      {report && <ReportView report={report} token={token} />}
    </div>
  );
}

function Monitor({ token, session, ppe, onEnd, onReset, onSessionUpdate }: { token: string; session: Session; ppe: PPE[]; onEnd: () => Promise<void>; onReset: () => Promise<void>; onSessionUpdate: (s: Session) => void }) {
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
  const intervalRef = useRef<number | undefined>(undefined);
  const streamRef = useRef<MediaStream | undefined>(undefined);
  const stoppingRef = useRef(false);
  const ppeName = useMemo(() => Object.fromEntries(ppe.map((item) => [item.code, item.name])), [ppe]);

  function stopMonitoring(finalStatus = "Sessão encerrada") {
    stoppingRef.current = true;
    inFlight.current = false;
    if (intervalRef.current) window.clearInterval(intervalRef.current);
    intervalRef.current = undefined;
    wsRef.current?.close();
    wsRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = undefined;
    const video = videoRef.current;
    if (video) {
      video.pause();
      video.srcObject = null;
    }
    const canvas = overlayRef.current;
    canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    setStatus(finalStatus);
  }

  async function handleEndSession() {
    if (ending) return;
    setEnding(true);
    stopMonitoring("Encerrando sessão...");
    try {
      await onEnd();
    } finally {
      setEnding(false);
    }
  }

  useEffect(() => {

    async function start() {
      stoppingRef.current = false;
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      const socket = new WebSocket(`${wsBase()}/api/ws/inference?token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(session.id)}`);
      wsRef.current = socket;
      socket.onopen = () => setStatus("Monitorando em tempo real");
      socket.onerror = () => setStatus("Falha no WebSocket");
      socket.onclose = () => { if (!stoppingRef.current) setStatus("WebSocket desconectado"); };
      socket.onmessage = (message) => {
        if (stoppingRef.current) return;
        inFlight.current = false;
        const parsed = JSON.parse(message.data);
        if (parsed.error) {
          setStatus(parsed.error);
          return;
        }
        const sent = frames.current.get(parsed.frame_id);
        const e2e = sent ? performance.now() - sent : parsed.server_total_ms;
        frames.current.delete(parsed.frame_id);
        setResult(parsed);
        setStatus(`Monitorando · ${parsed.detections?.length ?? 0} detecções · ${parsed.tracks?.length ?? 0} tracks`);
        setLatencies((items) => [...items.slice(-59), e2e]);
        drawOverlay(parsed);
        if (!stoppingRef.current) api<Session>(`/api/sessions/${session.id}`, token).then(onSessionUpdate).catch(() => undefined);
      };

      const interval = window.setInterval(() => {
        const video = videoRef.current;
        if (!video || socket.readyState !== WebSocket.OPEN || inFlight.current || video.videoWidth === 0) return;
        const capture = captureRef.current;
        const scale = 640 / video.videoWidth;
        capture.width = 640;
        capture.height = Math.round(video.videoHeight * scale);
        capture.getContext("2d")?.drawImage(video, 0, 0, capture.width, capture.height);
        const frameId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        frames.current.set(frameId, performance.now());
        inFlight.current = true;
        socket.send(JSON.stringify({ frame_id: frameId, captured_at_ms: Date.now(), image: capture.toDataURL("image/jpeg", 0.72) }));
      }, 250);
      intervalRef.current = interval;
    }

    function drawOverlay(next: FrameResult) {
      const canvas = overlayRef.current;
      const video = videoRef.current;
      if (!canvas || !video) return;
      canvas.width = video.clientWidth;
      canvas.height = video.clientHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const sx = canvas.width / next.image_width;
      const sy = canvas.height / next.image_height;
      next.detections.forEach((det) => {
        const [x1, y1, x2, y2] = det.box;
        const isPerson = det.class_name === "Person";
        ctx.strokeStyle = isPerson ? "#38bdf8" : det.evidence === -1 ? "#ef4444" : "#22c55e";
        ctx.lineWidth = isPerson ? 3 : 2;
        const drawX = canvas.width - x2 * sx;
        ctx.strokeRect(drawX, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy);
        ctx.fillStyle = ctx.strokeStyle;
        ctx.font = "13px Inter, sans-serif";
        ctx.fillText(`${det.track_id ?? ""} ${det.class_name} ${(det.confidence * 100).toFixed(0)}%`, drawX + 4, y1 * sy + 16);
      });
    }

    start().catch((err) => setStatus(err instanceof Error ? err.message : "Falha ao iniciar câmera"));
    return () => {
      stopMonitoring("Sessão encerrada");
    };
  }, [session.id, token]);

  const averageLatency = latencies.length ? latencies.reduce((a, b) => a + b, 0) / latencies.length : 0;
  return (
    <div>
      <div className="monitor-header">
        <div>
          <h1>Sessão {session.mode === "individual" ? "individual" : "em grupo"}</h1>
          <p className="muted">{status}</p>
        </div>
        <div className={`lock ${session.machine_locked ? "danger" : ""}`}>{session.machine_locked ? "CORTE SIMULADO" : "Máquina liberada"}</div>
      </div>
      <div className="video-wrap">
        <video ref={videoRef} muted playsInline />
        <canvas ref={overlayRef} />
      </div>
      <div className="metrics">
        <div><strong>{result?.inference_ms.toFixed(0) ?? 0} ms</strong><span>Inferência</span></div>
        <div><strong>{averageLatency.toFixed(0)} ms</strong><span>E2E média</span></div>
        <div><strong>{percentile(latencies, 0.5).toFixed(0)} ms</strong><span>p50</span></div>
        <div><strong>{percentile(latencies, 0.95).toFixed(0)} ms</strong><span>p95</span></div>
      </div>
      <div className="track-grid">
        {(result?.tracks ?? []).map((track) => (
          <div key={track.track_id} className={`track-card ${track.compliant ? "ok" : "alert"}`}>
            <strong>{track.track_id}</strong>
            {session.required_ppe.map((code) => {
              const item = track.ppe[code];
              return <span key={code}>{ppeName[code] ?? code}: {item?.state ?? "unknown"} · nível {item?.severity ?? 0}</span>;
            })}
          </div>
        ))}
      </div>
      <div className="actions">
        {session.machine_locked && <button onClick={onReset}>Reset manual</button>}
        <button className="danger-btn" disabled={ending} onClick={handleEndSession}>{ending ? "Encerrando..." : "Encerrar sessão"}</button>
      </div>
    </div>
  );
}

function TrackComplianceChart({ report }: { report: Report }) {
  const rows = report.track_summaries.slice(0, 6).map((track) => ({
    label: track.track_id,
    value: track.samples ? track.compliant_samples / track.samples * 100 : 0,
  }));
  const data = rows.length ? rows : [{ label: "Sem tracks", value: 0 }];
  return (
    <div className="chart-card wide">
      <div><strong>Conformidade por pessoa/track</strong><span>Percentual de amostras conformes</span></div>
      <div className="bar-list">
        {data.map((item) => (
          <div className="bar-row" key={item.label}>
            <span>{item.label}</span>
            <div className="bar-track"><i style={{ width: `${Math.max(2, item.value)}%` }} /></div>
            <b>{item.value.toFixed(1)}%</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function SeverityChart({ report }: { report: Report }) {
  const data = [1, 2, 3].map((level) => ({ label: `Nível ${level}`, value: report.events_by_severity[String(level)] ?? 0 }));
  const max = Math.max(1, ...data.map((item) => item.value));
  return (
    <div className="chart-card">
      <div><strong>Eventos por severidade</strong><span>Alertas, infrações e cortes</span></div>
      <svg viewBox="0 0 320 180" role="img" aria-label="Eventos por severidade">
        {data.map((item, index) => {
          const height = item.value / max * 110;
          const x = 44 + index * 92;
          const y = 136 - height;
          const color = ["#f59e0b", "#fb7185", "#ef4444"][index];
          return <g key={item.label}>
            <rect x={x} y={y} width="48" height={height || 2} rx="10" fill={color} />
            <text x={x + 24} y={y - 8} textAnchor="middle" fill="#dce7f7" fontSize="16" fontWeight="800">{item.value}</text>
            <text x={x + 24} y="160" textAnchor="middle" fill="#93a9c3" fontSize="12">{item.label}</text>
          </g>;
        })}
      </svg>
    </div>
  );
}

function LatencyChart({ report }: { report: Report }) {
  const data = [
    { label: "Média", value: report.latency.average_ms ?? 0 },
    { label: "p50", value: report.latency.p50_ms ?? 0 },
    { label: "p95", value: report.latency.p95_ms ?? 0 },
  ];
  const max = Math.max(1, ...data.map((item) => item.value));
  return (
    <div className="chart-card">
      <div><strong>Latência fim a fim</strong><span>Resumo operacional em ms</span></div>
      <div className="latency-bars">
        {data.map((item) => (
          <div key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value.toFixed(0)} ms</strong>
            <i style={{ width: `${Math.max(4, item.value / max * 100)}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ComplianceDonut({ report }: { report: Report }) {
  const value = Math.max(0, Math.min(100, report.compliance_percent));
  const circumference = 2 * Math.PI * 42;
  return (
    <div className="chart-card donut-card">
      <div><strong>Conformidade geral</strong><span>Aderência da sessão</span></div>
      <svg viewBox="0 0 120 120" role="img" aria-label="Conformidade geral">
        <circle cx="60" cy="60" r="42" fill="none" stroke="#19324d" strokeWidth="16" />
        <circle cx="60" cy="60" r="42" fill="none" stroke="#22c55e" strokeWidth="16" strokeLinecap="round" transform="rotate(-90 60 60)" strokeDasharray={`${circumference}`} strokeDashoffset={`${circumference * (1 - value / 100)}`} />
        <text x="60" y="58" textAnchor="middle" fill="#f8fbff" fontSize="20" fontWeight="900">{value.toFixed(1)}%</text>
        <text x="60" y="76" textAnchor="middle" fill="#93a9c3" fontSize="10">conforme</text>
      </svg>
    </div>
  );
}
function ReportView({ report, token }: { report: Report; token: string }) {
  return (
    <div className="report">
      <h2>Relatório final</h2>
      <div className="metrics">
        <div><strong>{report.duration_seconds.toFixed(1)} s</strong><span>Duração</span></div>
        <div><strong>{report.compliance_percent.toFixed(1)}%</strong><span>Conformidade</span></div>
        <div><strong>{report.infractions}</strong><span>Infrações</span></div>
        <div><strong>{report.machine_cuts}</strong><span>Cortes</span></div>
      </div>
      <div className="report-charts">
        <ComplianceDonut report={report} />
        <SeverityChart report={report} />
        <LatencyChart report={report} />
        <TrackComplianceChart report={report} />
      </div>
      <a className="download" href={`${API_BASE}/api/reports/${report.session_id}/pdf?token=${token}`} onClick={(event) => {
        event.preventDefault();
        fetch(`${API_BASE}/api/reports/${report.session_id}/pdf`, { headers: { Authorization: `Bearer ${token}` } })
          .then((response) => response.blob())
          .then((blob) => {
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `relatorio-${report.session_id}.pdf`;
            link.click();
            URL.revokeObjectURL(url);
          });
      }}>Baixar PDF</a>
    </div>
  );
}

function AdminPanel({ token, ppe }: { token: string; ppe: PPE[] }) {
  const [dashboard, setDashboard] = useState<any>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [jobs, setJobs] = useState<JobRole[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("senha123");
  const [presetName, setPresetName] = useState("");
  const [presetPpe, setPresetPpe] = useState<string[]>([]);

  async function load() {
    const [dash, u, pr, jr, ar] = await Promise.all([
      api("/api/dashboard", token),
      api<User[]>("/api/users", token),
      api<Preset[]>("/api/presets", token),
      api<JobRole[]>("/api/job-roles", token),
      api<Area[]>("/api/areas", token),
    ]);
    setDashboard(dash);
    setUsers(u);
    setPresets(pr);
    setJobs(jr);
    setAreas(ar);
  }

  useEffect(() => {
    load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div>
      <h2>Dashboard admin</h2>
      {dashboard && (
        <div className="metrics">
          <div><strong>{dashboard.users}</strong><span>Usuários</span></div>
          <div><strong>{dashboard.active_sessions}</strong><span>Sessões ativas</span></div>
          <div><strong>{dashboard.infractions}</strong><span>Infrações</span></div>
          <div><strong>{dashboard.average_latency_ms}</strong><span>Latência média</span></div>
        </div>
      )}
      <div className="admin-grid">
        <form onSubmit={async (event) => {
          event.preventDefault();
          await api("/api/users", token, { method: "POST", body: JSON.stringify({ name, username, password, role: "employee", job_role_id: jobs[0]?.id, area_id: areas[0]?.id }) });
          setName(""); setUsername("");
          await load();
        }}>
          <h3>Cadastrar funcionário</h3>
          <input placeholder="Nome" value={name} onChange={(event) => setName(event.target.value)} />
          <input placeholder="Login" value={username} onChange={(event) => setUsername(event.target.value)} />
          <input placeholder="Senha" value={password} onChange={(event) => setPassword(event.target.value)} />
          <button>Cadastrar</button>
        </form>
        <form onSubmit={async (event) => {
          event.preventDefault();
          await api("/api/presets", token, { method: "POST", body: JSON.stringify({ name: presetName, ppe_codes: presetPpe, active: true }) });
          setPresetName(""); setPresetPpe([]);
          await load();
        }}>
          <h3>Novo preset</h3>
          <input placeholder="Nome do preset" value={presetName} onChange={(event) => setPresetName(event.target.value)} />
          <div className="checks compact">
            {ppe.map((item) => (
              <label key={item.code}>
                <input type="checkbox" checked={presetPpe.includes(item.code)} onChange={(event) => setPresetPpe((current) => event.target.checked ? [...current, item.code] : current.filter((code) => code !== item.code))} />
                {item.name}
              </label>
            ))}
          </div>
          <button>Salvar preset</button>
        </form>
      </div>
      <h3>Funcionários</h3>
      <div className="table">
        {users.map((item) => <div key={item.id}><span>{item.name}</span><span>{item.username}</span><span>{item.active ? "Ativo" : "Inativo"}</span></div>)}
      </div>
      <h3>Presets</h3>
      <div className="table">
        {presets.map((item) => <div key={item.id}><span>{item.name}</span><span>{item.ppe_codes.join(", ")}</span><span>{item.active ? "Ativo" : "Inativo"}</span></div>)}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);











