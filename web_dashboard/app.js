'use strict';

const API = Object.freeze({
  gateway: 'https://apim-neko-game-nhom2-2026.azure-api.net/neko',
  health: 'https://apim-neko-game-nhom2-2026.azure-api.net/neko/health',
  version: 'https://apim-neko-game-nhom2-2026.azure-api.net/neko/version'
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
  elements.backendStatus = document.getElementById('backendStatus');
  elements.downloadLink = document.getElementById('downloadLink');
  elements.gatewayValue = document.getElementById('gatewayValue');
  elements.healthPayload = document.getElementById('healthPayload');
  elements.lastChecked = document.getElementById('lastChecked');
  elements.refreshButton = document.getElementById('refreshButton');
  elements.serviceValue = document.getElementById('serviceValue');
  elements.statusDot = document.getElementById('statusDot');
  elements.statusMessage = document.getElementById('statusMessage');
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
  setBackendStatus('checking', 'Đang gọi health endpoint qua Azure API Management.');
  setText(elements.serviceValue, 'Đang tải');
  setText(elements.versionValue, 'Đang tải');
  setText(elements.versionNote, '/version');
  setPayload({});

  const [healthResult, versionResult] = await Promise.allSettled([
    fetchJson(API.health),
    fetchJson(API.version)
  ]);

  handleHealthResult(healthResult);
  handleVersionResult(versionResult);

  elements.lastChecked.textContent = `Cập nhật: ${formatDateTime(new Date())}`;
  setLoadingState(false);
  isRefreshing = false;
}

function handleHealthResult(result) {
  if (result.status === 'fulfilled') {
    const healthData = result.value;
    setBackendStatus('online', 'Backend phản hồi thành công qua Azure API Management.');
    setText(elements.serviceValue, extractServiceName(healthData));
    setPayload(healthData);
    return;
  }

  setBackendStatus('offline', formatError(result.reason));
  setText(elements.serviceValue, 'Không truy cập được');
  setPayload({
    error: formatError(result.reason)
  });
}

function handleVersionResult(result) {
  if (result.status === 'fulfilled') {
    setText(elements.versionValue, extractVersion(result.value));
    setText(elements.versionNote, 'Nhận từ /version');
    return;
  }

  setText(elements.versionValue, 'Không truy cập được');
  setText(elements.versionNote, formatShortError(result.reason));
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

function extractServiceName(data) {
  if (typeof data === 'string') {
    return data;
  }

  if (!data || typeof data !== 'object') {
    return 'Không xác định';
  }

  const candidates = [
    data.service,
    data.serviceName,
    data.name,
    data.app,
    data.application
  ];

  const service = candidates.find((value) => typeof value === 'string' && value.trim());
  return service ? service.trim() : 'Không xác định';
}

function extractVersion(data) {
  if (typeof data === 'string') {
    return data;
  }

  if (!data || typeof data !== 'object') {
    return 'Không xác định';
  }

  const candidates = [
    data.version,
    data.backendVersion,
    data.backend_version,
    data.build,
    data.commit
  ];

  const version = candidates.find((value) => typeof value === 'string' && value.trim());
  return version ? version.trim() : 'Không xác định';
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
  elements.healthPayload.textContent = JSON.stringify(data, null, 2);
}

function setText(element, value) {
  element.textContent = value;
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
    return `API Management trả về ${error.status}. Backend có thể đang offline hoặc gateway chưa định tuyến đúng.`;
  }

  return 'Không thể kết nối tới API Management. Có thể backend offline, mất mạng hoặc CORS chưa cho phép website này.';
}
