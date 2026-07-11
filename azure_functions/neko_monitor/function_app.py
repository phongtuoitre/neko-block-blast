import json
import logging
import os
import time
import urllib.error
import urllib.request

import azure.functions as func


app = func.FunctionApp()

BACKEND_TIMEOUT_SECONDS = 10


def _backend_base_url() -> str:
    return os.environ.get("NEKO_API_BASE_URL", "").strip().rstrip("/")


def _job_key() -> str:
    return os.environ.get("NEKO_JOB_KEY", "").strip()


def _json_response(payload: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


def _parse_json_response(raw_body: bytes):
    if not raw_body:
        return None
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw_body.decode("utf-8", errors="replace")


def _call_backend(path: str, method: str = "GET", include_job_key: bool = False) -> dict:
    backend_url = _backend_base_url()
    if not backend_url:
        return {
            "ok": False,
            "backend_url": "",
            "status_code": None,
            "latency_ms": None,
            "data": None,
            "message": "NEKO_API_BASE_URL is not configured",
        }

    headers = {
        "Accept": "application/json",
        "User-Agent": "neko-monitor-function",
    }
    if include_job_key:
        job_key = _job_key()
        if not job_key:
            return {
                "ok": False,
                "backend_url": backend_url,
                "status_code": None,
                "latency_ms": None,
                "data": None,
                "message": "NEKO_JOB_KEY is not configured",
            }
        headers["X-Job-Key"] = job_key

    request_url = f"{backend_url}{path}"
    request_data = b"" if method.upper() in {"POST", "PUT", "PATCH"} else None
    request = urllib.request.Request(
        request_url,
        data=request_data,
        headers=headers,
        method=method.upper(),
    )
    started_at = time.perf_counter()

    try:
        with urllib.request.urlopen(request, timeout=BACKEND_TIMEOUT_SECONDS) as response:
            raw_body = response.read(1024 * 1024)
            status_code = response.getcode()
    except urllib.error.HTTPError as exc:
        raw_body = exc.read(1024 * 1024)
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        return {
            "ok": False,
            "backend_url": backend_url,
            "status_code": exc.code,
            "latency_ms": latency_ms,
            "data": _parse_json_response(raw_body),
            "message": f"Backend returned HTTP {exc.code}",
        }
    except urllib.error.URLError as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        return {
            "ok": False,
            "backend_url": backend_url,
            "status_code": None,
            "latency_ms": latency_ms,
            "data": None,
            "message": f"Backend request failed: {exc.reason}",
        }
    except TimeoutError:
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        return {
            "ok": False,
            "backend_url": backend_url,
            "status_code": None,
            "latency_ms": latency_ms,
            "data": None,
            "message": "Backend request timed out",
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        logging.exception("Unexpected backend request error")
        return {
            "ok": False,
            "backend_url": backend_url,
            "status_code": None,
            "latency_ms": latency_ms,
            "data": None,
            "message": f"Unexpected backend request error: {exc}",
        }

    latency_ms = round((time.perf_counter() - started_at) * 1000)
    return {
        "ok": 200 <= status_code < 300,
        "backend_url": backend_url,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "data": _parse_json_response(raw_body),
        "message": "Backend request OK"
        if 200 <= status_code < 300
        else f"Backend returned HTTP {status_code}",
    }


def _check_backend_health() -> dict:
    result = _call_backend("/health")
    return {
        "backend_url": result["backend_url"],
        "backend_ok": result["ok"],
        "status_code": result["status_code"],
        "latency_ms": result["latency_ms"],
        "message": "Backend is healthy" if result["ok"] else result["message"],
    }


def _proxy_backend_job(path: str, method: str = "GET") -> func.HttpResponse:
    result = _call_backend(path, method=method, include_job_key=True)
    if result["ok"] and isinstance(result["data"], dict):
        return _json_response(result["data"], status_code=result["status_code"] or 200)

    payload = {
        "backend_url": result["backend_url"],
        "backend_ok": result["ok"],
        "status_code": result["status_code"],
        "latency_ms": result["latency_ms"],
        "message": result["message"],
    }
    if result["data"] is not None:
        payload["backend_response"] = result["data"]
    return _json_response(payload, status_code=result["status_code"] or 500)


@app.route(route="monitor/health-check", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def manual_health_check(req: func.HttpRequest) -> func.HttpResponse:
    result = {
        "function": "manual_health_check",
        **_check_backend_health(),
    }
    return _json_response(result)


@app.route(route="jobs/summary", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def jobs_summary(req: func.HttpRequest) -> func.HttpResponse:
    return _proxy_backend_job("/jobs/summary")


@app.route(
    route="jobs/cleanup-expired-rooms",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def jobs_cleanup_expired_rooms(req: func.HttpRequest) -> func.HttpResponse:
    return _proxy_backend_job("/jobs/cleanup-expired-rooms", method="POST")


@app.route(
    route="jobs/leaderboard-online",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def jobs_leaderboard_online(req: func.HttpRequest) -> func.HttpResponse:
    return _proxy_backend_job("/jobs/leaderboard-online")


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Neko Block Blast - Cloud Operations Dashboard</title>
  <style>
    :root {
      --azure: #0078d4;
      --azure-dark: #005a9e;
      --violet: #7c3aed;
      --cyan: #06b6d4;
      --ink: #132033;
      --muted: #65758b;
      --line: rgba(19, 32, 51, 0.1);
      --card: rgba(255, 255, 255, 0.9);
      --good: #0f9f6e;
      --bad: #dc2626;
      --warn: #b7791f;
      --shadow: 0 18px 45px rgba(15, 23, 42, 0.12);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(0, 120, 212, 0.24), transparent 34rem),
        radial-gradient(circle at top right, rgba(124, 58, 237, 0.22), transparent 32rem),
        linear-gradient(135deg, #f7fbff 0%, #eef6ff 48%, #f7f2ff 100%);
    }

    .page {
      width: min(1180px, calc(100% - 48px));
      margin: 0 auto;
      padding: 36px 0 28px;
    }

    .hero {
      display: grid;
      grid-template-columns: 1.25fr 0.75fr;
      gap: 24px;
      align-items: stretch;
      margin-bottom: 22px;
    }

    .hero-main,
    .panel,
    .stat-card,
    .job-card {
      background: var(--card);
      border: 1px solid rgba(255, 255, 255, 0.72);
      border-radius: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(16px);
    }

    .hero-main {
      padding: 32px;
      position: relative;
      overflow: hidden;
    }

    .hero-main::after {
      content: "";
      position: absolute;
      right: -70px;
      top: -70px;
      width: 220px;
      height: 220px;
      border-radius: 999px;
      background: linear-gradient(135deg, rgba(0, 120, 212, 0.2), rgba(124, 58, 237, 0.18));
    }

    .eyebrow {
      color: var(--azure-dark);
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 0.78rem;
      margin-bottom: 12px;
    }

    h1 {
      font-size: clamp(2rem, 4vw, 4.2rem);
      line-height: 1;
      margin: 0;
      letter-spacing: -0.02em;
    }

    h1 span {
      display: block;
      color: var(--azure);
    }

    .subtitle {
      max-width: 650px;
      color: var(--muted);
      font-size: 1.06rem;
      line-height: 1.65;
      margin: 18px 0 0;
    }

    .status-panel {
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 16px;
    }

    .status-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 14px 0;
      border-bottom: 1px solid var(--line);
    }

    .status-row:last-child {
      border-bottom: 0;
    }

    .label {
      color: var(--muted);
      font-size: 0.92rem;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 6px 11px;
      border-radius: 999px;
      font-weight: 800;
      font-size: 0.82rem;
      white-space: nowrap;
      background: rgba(15, 159, 110, 0.12);
      color: var(--good);
    }

    .badge.offline {
      background: rgba(220, 38, 38, 0.12);
      color: var(--bad);
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin: 22px 0;
    }

    button {
      border: 0;
      border-radius: 14px;
      padding: 12px 16px;
      font: inherit;
      font-weight: 800;
      color: #fff;
      background: linear-gradient(135deg, var(--azure), var(--violet));
      box-shadow: 0 10px 22px rgba(0, 120, 212, 0.22);
      cursor: pointer;
      transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    }

    button:hover {
      transform: translateY(-1px);
      box-shadow: 0 14px 28px rgba(0, 120, 212, 0.28);
    }

    button:disabled {
      cursor: progress;
      opacity: 0.62;
      transform: none;
    }

    .secondary {
      color: var(--azure-dark);
      background: #fff;
      border: 1px solid rgba(0, 120, 212, 0.18);
      box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
    }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 22px;
    }

    .stat-card {
      padding: 20px;
      min-height: 118px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      border-left: 5px solid rgba(0, 120, 212, 0.78);
    }

    .stat-card:nth-child(3n + 2) {
      border-left-color: rgba(124, 58, 237, 0.78);
    }

    .stat-card:nth-child(3n) {
      border-left-color: rgba(6, 182, 212, 0.78);
    }

    .stat-title {
      color: var(--muted);
      font-weight: 700;
      font-size: 0.9rem;
    }

    .stat-value {
      font-size: 2rem;
      font-weight: 900;
      letter-spacing: -0.02em;
    }

    .layout {
      display: grid;
      grid-template-columns: 1.35fr 0.65fr;
      gap: 18px;
      align-items: start;
    }

    .panel {
      padding: 22px;
    }

    .panel h2 {
      margin: 0 0 16px;
      font-size: 1.2rem;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
    }

    th,
    td {
      text-align: left;
      padding: 13px 10px;
      border-bottom: 1px solid var(--line);
      font-size: 0.95rem;
    }

    th {
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    tr:last-child td {
      border-bottom: 0;
    }

    .empty {
      color: var(--muted);
      padding: 20px 10px;
    }

    .jobs {
      display: grid;
      gap: 12px;
    }

    .job-card {
      box-shadow: none;
      padding: 16px;
      border-color: var(--line);
      background: rgba(255, 255, 255, 0.72);
    }

    .job-title {
      font-weight: 900;
      margin-bottom: 6px;
    }

    .job-meta {
      color: var(--muted);
      font-size: 0.92rem;
    }

    .toast {
      position: fixed;
      right: 24px;
      bottom: 24px;
      width: min(390px, calc(100% - 48px));
      padding: 16px 18px;
      border-radius: 16px;
      background: #0f172a;
      color: #fff;
      box-shadow: 0 20px 50px rgba(15, 23, 42, 0.28);
      opacity: 0;
      pointer-events: none;
      transform: translateY(10px);
      transition: opacity 0.18s ease, transform 0.18s ease;
      z-index: 20;
    }

    .toast.show {
      opacity: 1;
      transform: translateY(0);
    }

    .toast.error {
      background: #7f1d1d;
    }

    footer {
      color: var(--muted);
      text-align: center;
      padding: 26px 0 4px;
      font-size: 0.92rem;
    }

    @media (max-width: 960px) {
      .hero,
      .layout {
        grid-template-columns: 1fr;
      }

      .stats-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 640px) {
      .page {
        width: min(100% - 28px, 1180px);
        padding-top: 18px;
      }

      .hero-main,
      .status-panel,
      .panel {
        padding: 20px;
        border-radius: 18px;
      }

      .stats-grid {
        grid-template-columns: 1fr;
      }

      th,
      td {
        padding: 10px 6px;
      }
    }
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="hero-main">
        <div class="eyebrow">Neko Block Blast</div>
        <h1>Neko Block Blast <span>Cloud Operations Dashboard</span></h1>
        <p class="subtitle">Serverless operations dashboard powered by Azure Functions, FastAPI, and Azure App Service.</p>
      </div>
      <aside class="status-panel panel">
        <div class="status-row">
          <span class="label">Azure Functions</span>
          <span class="badge">Running</span>
        </div>
        <div class="status-row">
          <span class="label">Backend API</span>
          <span id="backendBadge" class="badge offline">Checking</span>
        </div>
        <div class="status-row">
          <span class="label">Last updated</span>
          <strong id="lastUpdated">--</strong>
        </div>
      </aside>
    </section>

    <section class="actions" aria-label="Dashboard actions">
      <button id="refreshBtn" type="button">Refresh Dashboard</button>
      <button id="cleanupBtn" type="button">Run Cleanup Expired Rooms</button>
      <button id="leaderboardBtn" class="secondary" type="button">Reload Leaderboard</button>
    </section>

    <section class="stats-grid" aria-label="System stats">
      <article class="stat-card"><div class="stat-title">Backend Status</div><div id="statBackendStatus" class="stat-value">--</div></article>
      <article class="stat-card"><div class="stat-title">Backend Latency</div><div id="statLatency" class="stat-value">--</div></article>
      <article class="stat-card"><div class="stat-title">Total Users</div><div id="statUsers" class="stat-value">--</div></article>
      <article class="stat-card"><div class="stat-title">Total Rooms</div><div id="statRooms" class="stat-value">--</div></article>
      <article class="stat-card"><div class="stat-title">Waiting Rooms</div><div id="statWaitingRooms" class="stat-value">--</div></article>
      <article class="stat-card"><div class="stat-title">Playing Rooms</div><div id="statPlayingRooms" class="stat-value">--</div></article>
      <article class="stat-card"><div class="stat-title">Finished Rooms</div><div id="statFinishedRooms" class="stat-value">--</div></article>
      <article class="stat-card"><div class="stat-title">Total Matches</div><div id="statMatches" class="stat-value">--</div></article>
      <article class="stat-card"><div class="stat-title">Finished Matches</div><div id="statFinishedMatches" class="stat-value">--</div></article>
    </section>

    <section class="layout">
      <div class="panel">
        <h2>Online Leaderboard</h2>
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Player</th>
              <th>Wins</th>
              <th>Matches</th>
              <th>Total Score</th>
            </tr>
          </thead>
          <tbody id="leaderboardBody">
            <tr><td colspan="5" class="empty">Loading leaderboard...</td></tr>
          </tbody>
        </table>
      </div>

      <aside class="panel">
        <h2>Serverless Jobs</h2>
        <div class="jobs">
          <div class="job-card">
            <div class="job-title">Health Monitor</div>
            <div class="job-meta">Enabled / Serverless / Timer Trigger / Every 5 minutes</div>
          </div>
          <div class="job-card">
            <div class="job-title">Room Cleanup</div>
            <div class="job-meta">Enabled / Serverless / Timer Trigger / Every 5 minutes</div>
          </div>
          <div class="job-card">
            <div class="job-title">Game Stats Timer</div>
            <div class="job-meta">Enabled / Serverless / Timer Trigger / Every 30 minutes</div>
          </div>
        </div>
      </aside>
    </section>

    <footer>Neko Block Blast Cloud Demo - Azure Functions + FastAPI + PostgreSQL</footer>
  </main>

  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script>
    const endpoints = {
      health: "/api/monitor/health-check",
      summary: "/api/jobs/summary",
      leaderboard: "/api/jobs/leaderboard-online",
      cleanup: "/api/jobs/cleanup-expired-rooms"
    };

    const els = {
      backendBadge: document.getElementById("backendBadge"),
      lastUpdated: document.getElementById("lastUpdated"),
      backendStatus: document.getElementById("statBackendStatus"),
      latency: document.getElementById("statLatency"),
      users: document.getElementById("statUsers"),
      rooms: document.getElementById("statRooms"),
      waitingRooms: document.getElementById("statWaitingRooms"),
      playingRooms: document.getElementById("statPlayingRooms"),
      finishedRooms: document.getElementById("statFinishedRooms"),
      matches: document.getElementById("statMatches"),
      finishedMatches: document.getElementById("statFinishedMatches"),
      leaderboardBody: document.getElementById("leaderboardBody"),
      refreshBtn: document.getElementById("refreshBtn"),
      cleanupBtn: document.getElementById("cleanupBtn"),
      leaderboardBtn: document.getElementById("leaderboardBtn"),
      toast: document.getElementById("toast")
    };

    function setText(element, value) {
      element.textContent = value === null || value === undefined || value === "" ? "--" : value;
    }

    function formatNumber(value) {
      const number = Number(value || 0);
      return Number.isFinite(number) ? number.toLocaleString() : "--";
    }

    function markBackend(online, message) {
      els.backendBadge.textContent = online ? "Online" : "Offline";
      els.backendBadge.classList.toggle("offline", !online);
      setText(els.backendStatus, online ? "Online" : "Offline");
      if (message && !online) {
        showToast(message, true);
      }
    }

    function updateLastUpdated() {
      els.lastUpdated.textContent = new Date().toLocaleString();
    }

    function showToast(message, isError = false) {
      els.toast.textContent = message;
      els.toast.classList.toggle("error", isError);
      els.toast.classList.add("show");
      window.clearTimeout(showToast.timer);
      showToast.timer = window.setTimeout(() => {
        els.toast.classList.remove("show");
      }, 4200);
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, {
        cache: "no-store",
        ...options
      });
      const text = await response.text();
      let payload = {};
      if (text) {
        try {
          payload = JSON.parse(text);
        } catch (error) {
          payload = { message: text };
        }
      }
      if (!response.ok) {
        throw new Error(payload.message || payload.detail || `Request failed with HTTP ${response.status}`);
      }
      return payload;
    }

    async function refreshHealth() {
      const data = await fetchJson(endpoints.health);
      const isOnline = Boolean(data.backend_ok);
      markBackend(isOnline, isOnline ? "" : data.message || "Backend health check failed");
      setText(els.latency, data.latency_ms === null || data.latency_ms === undefined ? "--" : `${data.latency_ms} ms`);
      return data;
    }

    async function refreshSummary() {
      const data = await fetchJson(endpoints.summary);
      setText(els.users, formatNumber(data.total_users));
      setText(els.rooms, formatNumber(data.total_rooms));
      setText(els.waitingRooms, formatNumber(data.waiting_rooms));
      setText(els.playingRooms, formatNumber(data.playing_rooms));
      setText(els.finishedRooms, formatNumber(data.finished_rooms));
      setText(els.matches, formatNumber(data.total_matches));
      setText(els.finishedMatches, formatNumber(data.finished_matches));
      return data;
    }

    async function refreshLeaderboard() {
      const data = await fetchJson(endpoints.leaderboard);
      const rows = Array.isArray(data.leaderboard) ? data.leaderboard : [];
      if (!rows.length) {
        els.leaderboardBody.innerHTML = '<tr><td colspan="5" class="empty">No online match data yet.</td></tr>';
        return data;
      }
      els.leaderboardBody.innerHTML = rows.map((row, index) => `
        <tr>
          <td>${index + 1}</td>
          <td>${escapeHtml(row.display_name || row.username || "Player")}</td>
          <td>${formatNumber(row.wins)}</td>
          <td>${formatNumber(row.matches)}</td>
          <td>${formatNumber(row.total_score)}</td>
        </tr>
      `).join("");
      return data;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    async function refreshDashboard() {
      setBusy(true);
      updateLastUpdated();
      const results = await Promise.allSettled([
        refreshHealth(),
        refreshSummary(),
        refreshLeaderboard()
      ]);
      const failed = results.find((result) => result.status === "rejected");
      if (failed) {
        console.error("Dashboard refresh failed", failed.reason);
        markBackend(false, failed.reason.message || "Dashboard API request failed");
      }
      setBusy(false);
    }

    async function runCleanup() {
      els.cleanupBtn.disabled = true;
      try {
        const data = await fetchJson(endpoints.cleanup, { method: "POST" });
        showToast(`Cleanup completed successfully. Expired rooms processed: ${formatNumber(data.expired_rooms)}`);
        await Promise.allSettled([refreshSummary(), refreshLeaderboard()]);
      } catch (error) {
        console.error("Cleanup failed", error);
        markBackend(false, error.message || "Cleanup request failed");
      } finally {
        els.cleanupBtn.disabled = false;
        updateLastUpdated();
      }
    }

    function setBusy(isBusy) {
      els.refreshBtn.disabled = isBusy;
      els.leaderboardBtn.disabled = isBusy;
    }

    els.refreshBtn.addEventListener("click", refreshDashboard);
    els.cleanupBtn.addEventListener("click", runCleanup);
    els.leaderboardBtn.addEventListener("click", async () => {
      try {
        await refreshLeaderboard();
        updateLastUpdated();
        showToast("Leaderboard reloaded");
      } catch (error) {
        console.error("Leaderboard reload failed", error);
        markBackend(false, error.message || "Leaderboard request failed");
      }
    });

    refreshDashboard();
  </script>
</body>
</html>"""


@app.route(route="demo/dashboard", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def cloud_operations_dashboard(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        _dashboard_html(),
        status_code=200,
        mimetype="text/html",
    )


@app.timer_trigger(
    schedule="0 */5 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def health_monitor_timer(timer: func.TimerRequest) -> None:
    result = _check_backend_health()
    if result["backend_ok"]:
        logging.info(
            "Backend health OK url=%s status_code=%s latency_ms=%s",
            result["backend_url"],
            result["status_code"],
            result["latency_ms"],
        )
        return

    logging.warning(
        "Backend health FAILED url=%s status_code=%s latency_ms=%s message=%s",
        result["backend_url"],
        result["status_code"],
        result["latency_ms"],
        result["message"],
    )


@app.timer_trigger(
    schedule="0 */5 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def room_cleanup_timer(timer: func.TimerRequest) -> None:
    result = _call_backend(
        "/jobs/cleanup-expired-rooms",
        method="POST",
        include_job_key=True,
    )
    if result["ok"]:
        logging.info(
            "Expired room cleanup OK status_code=%s latency_ms=%s response=%s",
            result["status_code"],
            result["latency_ms"],
            result["data"],
        )
        return

    logging.warning(
        "Expired room cleanup FAILED status_code=%s latency_ms=%s message=%s response=%s",
        result["status_code"],
        result["latency_ms"],
        result["message"],
        result["data"],
    )


@app.timer_trigger(
    schedule="0 */30 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def game_stats_timer(timer: func.TimerRequest) -> None:
    result = _call_backend("/jobs/summary", include_job_key=True)
    if result["ok"] and isinstance(result["data"], dict):
        stats = result["data"]
        logging.info(
            "Game stats OK users=%s rooms=%s matches=%s playing_matches=%s",
            stats.get("total_users"),
            stats.get("total_rooms"),
            stats.get("total_matches"),
            stats.get("playing_matches"),
        )
        return

    logging.warning(
        "Game stats FAILED status_code=%s latency_ms=%s message=%s response=%s",
        result["status_code"],
        result["latency_ms"],
        result["message"],
        result["data"],
    )
