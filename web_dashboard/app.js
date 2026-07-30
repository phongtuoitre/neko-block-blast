'use strict';

const API_BASE = 'https://apim-neko-game-nhom2-2026.azure-api.net/neko';
const API = Object.freeze({
  gateway: API_BASE,
  health: `${API_BASE}/health`,
  version: `${API_BASE}/version`,
  leaderboard: `${API_BASE}/jobs/leaderboard-online`
});

const DOWNLOAD_URL = 'https://nekoblockblastnhom2.blob.core.windows.net/game-demo/NekoBlockBlast.exe';
const REQUEST_TIMEOUT_MS = 10000;

const elements = {};
let isRefreshing = false;

document.addEventListener('DOMContentLoaded', () => {
  cacheElements();
  hydrateStaticValues();

  elements.refreshButton.addEventListener('click', refreshDashboard);
  refreshDashboard();
});

function cacheElements() {
  elements.apiPayload = document.getElementById('apiPayload');
  elements.backendStatus = document.getElementById('backendStatus');
  elements.deploySourceValue = document.getElementById('deploySourceValue');
  elements.downloadLink = document.getElementById('downloadLink');
  elements.gatewayValue = document.getElementById('gatewayValue');
  elements.lastChecked = document.getElementById('lastChecked');
  elements.leaderboardBody = document.getElementById('leaderboardBody');
  elements.leaderboardCaption = document.getElementById('leaderboardCaption');
  elements.leaderboardStatus = document.getElementById('leaderboardStatus');
  elements.refreshButton = document.getElementById('refreshButton');
  elements.serviceValue = document.getElementById('serviceValue');
  elements.statusDot = document.getElementById('statusDot');
  elements.statusMessage = document.getElementById('statusMessage');
  elements.topMatchesValue = document.getElementById('topMatchesValue');
  elements.topScoreValue = document.getElementById('topScoreValue');
  elements.topWinsValue = document.getElementById('topWinsValue');
  elements.versionNote = document.getElementById('versionNote');
  elements.versionValue = document.getElementById('versionValue');
}

function hydrateStaticValues() {
  elements.downloadLink.href = DOWNLOAD_URL;
  elements.gatewayValue.textContent = API.gateway;
}

async function refreshDashboard() {
  if (isRefreshing) {
    return;
  }

  isRefreshing = true;
  setLoadingState(true);
  setBackendStatus('checking', 'Đang gọi /health qua Azure API Management.');
  setText(elements.serviceValue, 'Đang tải');
  setText(elements.versionValue, 'Đang tải');
  setText(elements.deploySourceValue, 'Đang tải');
  setText(elements.versionNote, 'Từ JSON /version');
  setLeaderboardLoading();
  setAchievementLoading();
  setPayload({});

  const [healthResult, versionResult, leaderboardResult] = await Promise.allSettled([
    fetchJson(API.health),
    fetchJson(API.version),
    fetchJson(API.leaderboard)
  ]);

  const payload = {
    health: normalizeSettledResult(healthResult),
    version: normalizeSettledResult(versionResult),
    leaderboard: normalizeSettledResult(leaderboardResult)
  };

  handleHealthResult(healthResult);
  handleVersionResult(versionResult);
  handleLeaderboardResult(leaderboardResult);

  elements.lastChecked.textContent = `Cập nhật: ${formatDateTime(new Date())}`;
  setPayload(payload);
  setLoadingState(false);
  isRefreshing = false;
}

function handleHealthResult(result) {
  if (result.status === 'fulfilled') {
    const healthData = result.value;
    const service = typeof healthData.service === 'string' ? healthData.service : 'Không xác định';
    setBackendStatus('online', 'Backend phản hồi thành công qua /health.');
    setText(elements.serviceValue, service);
    return;
  }

  setBackendStatus('offline', formatError(result.reason));
  setText(elements.serviceValue, 'Không truy cập được');
}

function handleVersionResult(result) {
  if (result.status === 'fulfilled') {
    const versionData = result.value;
    setText(elements.versionValue, readStringField(versionData, 'version'));
    setText(elements.deploySourceValue, readStringField(versionData, 'deploy_from'));
    setText(elements.versionNote, 'Nhận từ GET /version');
    return;
  }

  setText(elements.versionValue, 'Không truy cập được');
  setText(elements.deploySourceValue, 'Không truy cập được');
  setText(elements.versionNote, formatShortError(result.reason));
}

function handleLeaderboardResult(result) {
  if (result.status !== 'fulfilled') {
    renderLeaderboardError(result.reason);
    setAchievementUnavailable(result.reason);
    return;
  }

  const rows = Array.isArray(result.value.leaderboard) ? result.value.leaderboard : [];
  renderLeaderboard(rows);
  renderAchievementSummary(rows);
}

async function fetchJson(url) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'GET',
      cache: 'no-store',
      headers: {
        Accept: 'application/json'
      },
      signal: controller.signal
    });

    const bodyText = await response.text();
    const data = parseJsonBody(bodyText);

    if (!response.ok) {
      const error = new Error(`HTTP ${response.status} ${response.statusText || ''}`.trim());
      error.status = response.status;
      error.data = data;
      error.url = url;
      throw error;
    }

    return data;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function parseJsonBody(bodyText) {
  if (!bodyText) {
    return {};
  }

  try {
    return JSON.parse(bodyText);
  } catch (error) {
    return {
      raw: bodyText
    };
  }
}

function renderLeaderboard(rows) {
  elements.leaderboardBody.replaceChildren();
  setPill(elements.leaderboardStatus, 'Online', 'pill-online');

  if (rows.length === 0) {
    appendEmptyLeaderboardRow('API trả về leaderboard rỗng.');
    elements.leaderboardCaption.textContent = 'GET /jobs/leaderboard-online trả về {"leaderboard":[]}.';
    return;
  }

  rows.forEach((row, index) => {
    const tr = document.createElement('tr');
    appendCell(tr, `#${index + 1}`);
    appendPlayerCell(tr, row);
    appendCell(tr, formatNumber(row.wins));
    appendCell(tr, formatNumber(row.matches));
    appendCell(tr, formatNumber(row.total_score));
    elements.leaderboardBody.appendChild(tr);
  });

  elements.leaderboardCaption.textContent =
    'Dữ liệu từ GET /jobs/leaderboard-online: user_id, username, display_name, wins, matches, total_score.';
}

function renderLeaderboardError(error) {
  elements.leaderboardBody.replaceChildren();

  if (requiresBackendSecret(error)) {
    setPill(elements.leaderboardStatus, 'Cần X-Job-Key', 'pill-locked');
    appendEmptyLeaderboardRow(
      'Endpoint /jobs/leaderboard-online yêu cầu X-Job-Key. Dashboard không nhúng key hoặc secret trong frontend.'
    );
    elements.leaderboardCaption.textContent =
      'Không gửi X-Job-Key từ frontend, nên bảng xếp hạng chỉ hiển thị khi backend/APIM có endpoint public riêng.';
    return;
  }

  setPill(elements.leaderboardStatus, 'Lỗi', 'pill-offline');
  appendEmptyLeaderboardRow(formatError(error));
  elements.leaderboardCaption.textContent = 'Không thể tải leaderboard qua APIM.';
}

function renderAchievementSummary(rows) {
  if (rows.length === 0) {
    setText(elements.topScoreValue, 'Chưa có dữ liệu');
    setText(elements.topMatchesValue, 'Chưa có dữ liệu');
    setText(elements.topWinsValue, 'Chưa có dữ liệu');
    return;
  }

  const topScore = maxBy(rows, (row) => numberValue(row.total_score));
  const topMatches = maxBy(rows, (row) => numberValue(row.matches));
  const topWins = maxBy(rows, (row) => numberValue(row.wins));

  setText(elements.topScoreValue, formatMetricWithPlayer(topScore, 'total_score'));
  setText(elements.topMatchesValue, formatMetricWithPlayer(topMatches, 'matches'));
  setText(elements.topWinsValue, formatMetricWithPlayer(topWins, 'wins'));
}

function setAchievementLoading() {
  setText(elements.topScoreValue, 'Đang tải');
  setText(elements.topMatchesValue, 'Đang tải');
  setText(elements.topWinsValue, 'Đang tải');
}

function setAchievementUnavailable(error) {
  const value = requiresBackendSecret(error) ? 'Cần X-Job-Key' : 'Không truy cập được';
  setText(elements.topScoreValue, value);
  setText(elements.topMatchesValue, value);
  setText(elements.topWinsValue, value);
}

function setLeaderboardLoading() {
  setPill(elements.leaderboardStatus, 'Đang tải', 'pill-checking');
  elements.leaderboardBody.replaceChildren();
  appendEmptyLeaderboardRow('Đang tải bảng xếp hạng...');
  elements.leaderboardCaption.textContent = 'Endpoint đã xác minh: GET /jobs/leaderboard-online.';
}

function appendEmptyLeaderboardRow(message) {
  const tr = document.createElement('tr');
  const td = document.createElement('td');
  td.colSpan = 5;
  td.className = 'empty-cell';
  td.textContent = message;
  tr.appendChild(td);
  elements.leaderboardBody.appendChild(tr);
}

function appendPlayerCell(tr, row) {
  const td = document.createElement('td');
  const wrapper = document.createElement('span');
  const name = document.createElement('strong');
  const username = document.createElement('small');

  wrapper.className = 'player-cell';
  name.textContent = readStringField(row, 'display_name');
  username.textContent = readStringField(row, 'username');

  wrapper.appendChild(name);
  wrapper.appendChild(username);
  td.appendChild(wrapper);
  tr.appendChild(td);
}

function appendCell(tr, value) {
  const td = document.createElement('td');
  td.textContent = value;
  tr.appendChild(td);
}

function setBackendStatus(state, message) {
  const labels = {
    checking: 'Đang kiểm tra',
    online: 'Online',
    offline: 'Offline'
  };

  document.body.dataset.backendStatus = state;
  elements.backendStatus.textContent = labels[state] || labels.checking;
  elements.statusMessage.textContent = message;
  elements.statusDot.className = `status-dot state-${state}`;
}

function setLoadingState(isLoading) {
  elements.refreshButton.disabled = isLoading;
  elements.refreshButton.textContent = isLoading ? 'Đang kiểm tra...' : 'Kiểm tra lại';
  elements.refreshButton.setAttribute('aria-busy', String(isLoading));
}

function setPayload(data) {
  elements.apiPayload.textContent = JSON.stringify(data, null, 2);
}

function setPill(element, label, className) {
  element.textContent = label;
  element.className = `pill ${className}`;
}

function setText(element, value) {
  element.textContent = value;
}

function normalizeSettledResult(result) {
  if (result.status === 'fulfilled') {
    return {
      ok: true,
      data: result.value
    };
  }

  return {
    ok: false,
    error: formatError(result.reason),
    status: result.reason && result.reason.status ? result.reason.status : null,
    data: result.reason && result.reason.data ? result.reason.data : null
  };
}

function readStringField(data, fieldName) {
  if (!data || typeof data !== 'object') {
    return 'Không xác định';
  }

  const value = data[fieldName];
  return typeof value === 'string' && value.trim() ? value.trim() : 'Không xác định';
}

function requiresBackendSecret(error) {
  return Boolean(error && (error.status === 401 || error.status === 403 || error.status === 503));
}

function numberValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function maxBy(rows, selector) {
  return rows.reduce((best, row) => (selector(row) > selector(best) ? row : best), rows[0]);
}

function formatMetricWithPlayer(row, fieldName) {
  const name = readStringField(row, 'display_name');
  return `${formatNumber(row[fieldName])} - ${name}`;
}

function formatNumber(value) {
  return new Intl.NumberFormat('vi-VN').format(numberValue(value));
}

function formatDateTime(date) {
  return new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'short',
    timeStyle: 'medium'
  }).format(date);
}

function formatShortError(error) {
  if (error && error.status) {
    return `HTTP ${error.status}`;
  }

  if (error && error.name === 'AbortError') {
    return 'Hết thời gian chờ';
  }

  return 'Không thể kết nối';
}

function formatError(error) {
  if (error && error.name === 'AbortError') {
    return 'Không nhận được phản hồi từ API Management trong thời gian chờ.';
  }

  if (error && error.status) {
    const detail = error.data && error.data.detail ? ` Chi tiết: ${error.data.detail}` : '';
    return `API Management trả về HTTP ${error.status}.${detail}`;
  }

  return 'Không thể kết nối tới API Management. Có thể backend offline, mất mạng hoặc CORS chưa cho phép website này.';
}
