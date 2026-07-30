'use strict';

const API_BASE = 'https://apim-neko-game-nhom2-2026.azure-api.net/neko';
const API = Object.freeze({
  gateway: API_BASE,
  health: `${API_BASE}/health`,
  version: `${API_BASE}/version`,
  dashboard: `${API_BASE}/public/dashboard`
});

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
  elements.backendStatus = document.getElementById('backendStatus');
  elements.dashboardUpdatedAt = document.getElementById('dashboardUpdatedAt');
  elements.deploySourceValue = document.getElementById('deploySourceValue');
  elements.gatewayValue = document.getElementById('gatewayValue');
  elements.highestScoreName = document.getElementById('highestScoreName');
  elements.highestScoreValue = document.getElementById('highestScoreValue');
  elements.lastChecked = document.getElementById('lastChecked');
  elements.leaderboardBody = document.getElementById('leaderboardBody');
  elements.mostMatchesName = document.getElementById('mostMatchesName');
  elements.mostMatchesValue = document.getElementById('mostMatchesValue');
  elements.mostWinsName = document.getElementById('mostWinsName');
  elements.mostWinsValue = document.getElementById('mostWinsValue');
  elements.recentMatchesBody = document.getElementById('recentMatchesBody');
  elements.recentTimeHeader = document.getElementById('recentTimeHeader');
  elements.refreshButton = document.getElementById('refreshButton');
  elements.serviceValue = document.getElementById('serviceValue');
  elements.statusDot = document.getElementById('statusDot');
  elements.statusMessage = document.getElementById('statusMessage');
  elements.versionValue = document.getElementById('versionValue');
}

function hydrateStaticValues() {
  elements.gatewayValue.textContent = API.gateway;
}

async function refreshDashboard() {
  if (isRefreshing) {
    return;
  }

  isRefreshing = true;
  setLoadingState(true);
  setBackendStatus('checking', 'Đang kiểm tra trạng thái backend.');
  setText(elements.serviceValue, 'Đang tải');
  setText(elements.versionValue, 'Đang tải');
  setText(elements.deploySourceValue, 'Đang tải');
  setDashboardLoading();

  const [healthResult, versionResult, dashboardResult] = await Promise.allSettled([
    fetchJson(API.health),
    fetchJson(API.version),
    fetchJson(API.dashboard)
  ]);

  handleHealthResult(healthResult);
  handleVersionResult(versionResult);
  handleDashboardResult(dashboardResult);

  elements.lastChecked.textContent = `Cập nhật: ${formatDateTime(new Date())}`;
  setLoadingState(false);
  isRefreshing = false;
}

function handleHealthResult(result) {
  if (result.status === 'fulfilled') {
    const healthData = result.value;
    const service = readStringField(healthData, 'service');
    setBackendStatus('online', 'Backend đang phản hồi bình thường.');
    setText(elements.serviceValue, service);
    return;
  }

  setBackendStatus('offline', 'Không thể kết nối backend. Vui lòng kiểm tra lại sau.');
  setText(elements.serviceValue, 'Không truy cập được');
}

function handleVersionResult(result) {
  if (result.status === 'fulfilled') {
    const versionData = result.value;
    const deploySource = readStringField(versionData, 'deploy_from');
    setText(elements.versionValue, readStringField(versionData, 'version'));
    setText(elements.deploySourceValue, deploySource);
    return;
  }

  setText(elements.versionValue, 'Không truy cập được');
  setText(elements.deploySourceValue, 'Chưa có thông tin');
}

function handleDashboardResult(result) {
  if (result.status !== 'fulfilled') {
    setDashboardUnavailable();
    return;
  }

  const data = result.value;
  renderHighlights(data.highlights || {});
  renderLeaderboard(Array.isArray(data.leaderboard) ? data.leaderboard : []);
  renderRecentMatches(Array.isArray(data.recent_matches) ? data.recent_matches : []);
  setDashboardUpdatedAt(data.updated_at);
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
      throw new Error(`HTTP ${response.status}`);
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
    return {};
  }
}

function setDashboardLoading() {
  setHighlight(elements.highestScoreValue, elements.highestScoreName, null, 'điểm');
  setHighlight(elements.mostMatchesValue, elements.mostMatchesName, null, 'trận');
  setHighlight(elements.mostWinsValue, elements.mostWinsName, null, 'trận thắng');
  setText(elements.dashboardUpdatedAt, 'Đang tải');
  elements.dashboardUpdatedAt.className = 'pill pill-checking';
  replaceTableWithMessage(elements.leaderboardBody, 6, 'Đang tải bảng xếp hạng...');
  replaceTableWithMessage(elements.recentMatchesBody, 5, 'Đang tải trận gần đây...');
  setRecentTimeColumn(true);
}

function setDashboardUnavailable() {
  setHighlight(elements.highestScoreValue, elements.highestScoreName, null, 'điểm');
  setHighlight(elements.mostMatchesValue, elements.mostMatchesName, null, 'trận');
  setHighlight(elements.mostWinsValue, elements.mostWinsName, null, 'trận thắng');
  replaceTableWithMessage(elements.leaderboardBody, 6, 'Chưa có dữ liệu xếp hạng.');
  replaceTableWithMessage(elements.recentMatchesBody, 5, 'Chưa có trận đấu hoàn thành.');
  setText(elements.dashboardUpdatedAt, 'Chưa có dữ liệu');
  elements.dashboardUpdatedAt.className = 'pill pill-neutral';
  setRecentTimeColumn(true);
}

function renderHighlights(highlights) {
  setHighlight(
    elements.highestScoreValue,
    elements.highestScoreName,
    highlights.highest_score,
    'điểm'
  );
  setHighlight(
    elements.mostMatchesValue,
    elements.mostMatchesName,
    highlights.most_matches,
    'trận'
  );
  setHighlight(
    elements.mostWinsValue,
    elements.mostWinsName,
    highlights.most_wins,
    'trận thắng'
  );
}

function setHighlight(valueElement, nameElement, highlight, unit) {
  if (!highlight || !highlight.display_name) {
    setText(valueElement, 'Chưa có dữ liệu');
    setText(nameElement, unit);
    return;
  }

  setText(valueElement, formatNumber(highlight.value));
  setText(nameElement, `${highlight.display_name} - ${unit}`);
}

function renderLeaderboard(rows) {
  elements.leaderboardBody.replaceChildren();

  if (rows.length === 0) {
    replaceTableWithMessage(elements.leaderboardBody, 6, 'Chưa có dữ liệu xếp hạng.');
    return;
  }

  rows.forEach((row, index) => {
    const tr = document.createElement('tr');
    appendCell(tr, `#${row.rank || index + 1}`);
    appendPlayerCell(tr, row);
    appendCell(tr, formatNumber(row.matches));
    appendCell(tr, formatNumber(row.wins));
    appendCell(tr, formatNumber(row.total_score));
    appendCell(tr, formatNumber(row.best_score));
    elements.leaderboardBody.appendChild(tr);
  });
}

function renderRecentMatches(rows) {
  const hasTimestamp = rows.some((row) => Boolean(row.finished_at));
  const colSpan = hasTimestamp ? 5 : 4;
  elements.recentMatchesBody.replaceChildren();
  setRecentTimeColumn(hasTimestamp);

  if (rows.length === 0) {
    replaceTableWithMessage(
      elements.recentMatchesBody,
      colSpan,
      'Chưa có trận đấu hoàn thành.'
    );
    return;
  }

  rows.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, `#${row.match_id}`);
    appendCell(tr, row.mode || 'Không xác định');
    appendCell(tr, row.winner_display_name || 'Hòa');
    appendCell(tr, formatNumber(row.top_score));
    if (hasTimestamp) {
      appendCell(tr, row.finished_at ? formatDateTime(new Date(row.finished_at)) : '');
    }
    elements.recentMatchesBody.appendChild(tr);
  });
}

function setDashboardUpdatedAt(value) {
  if (!value) {
    setText(elements.dashboardUpdatedAt, 'Chưa có dữ liệu');
    elements.dashboardUpdatedAt.className = 'pill pill-neutral';
    return;
  }

  setText(elements.dashboardUpdatedAt, `Cập nhật ${formatDateTime(new Date(value))}`);
  elements.dashboardUpdatedAt.className = 'pill pill-online';
}

function appendPlayerCell(tr, row) {
  const td = document.createElement('td');
  const wrapper = document.createElement('span');
  const name = document.createElement('strong');
  const username = document.createElement('small');

  wrapper.className = 'player-cell';
  name.textContent = row.display_name || 'Không xác định';
  username.textContent = row.username || '';

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

function replaceTableWithMessage(tbody, colSpan, message) {
  const tr = document.createElement('tr');
  const td = document.createElement('td');
  td.colSpan = colSpan;
  td.className = 'empty-cell';
  td.textContent = message;
  tr.appendChild(td);
  tbody.replaceChildren(tr);
}

function setRecentTimeColumn(isVisible) {
  elements.recentTimeHeader.hidden = !isVisible;
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

function setText(element, value) {
  element.textContent = value;
}

function readStringField(data, fieldName) {
  if (!data || typeof data !== 'object') {
    return 'Không xác định';
  }

  const value = data[fieldName];
  return typeof value === 'string' && value.trim() ? value.trim() : 'Không xác định';
}

function formatNumber(value) {
  const number = Number(value);
  return new Intl.NumberFormat('vi-VN').format(Number.isFinite(number) ? number : 0);
}

function formatDateTime(date) {
  if (Number.isNaN(date.getTime())) {
    return '';
  }

  return new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'short',
    timeStyle: 'medium'
  }).format(date);
}
