const ui = {
  dashboard: null,
  config: null,
  jsonTab: "received",
  selectedSource: "",
  polling: false,
  toastTimer: null,
};

const stateLabels = {
  pass: "ĐI ĐƯỢC",
  blocked: "BỊ CHẶN",
  unknown: "CHƯA XÁC ĐỊNH",
  warming_up: "ĐANG KHỞI ĐỘNG",
  error: "LỖI",
};

const reasonLabels = {
  occupancy_threshold_exceeded: "Vượt ngưỡng chiếm dụng",
  insufficient_clearance: "Không đủ độ rộng",
  route_disconnected: "Đường đi không liên thông",
  camera_disconnected: "Mất kết nối camera",
  calibration_missing: "Thiếu calibration",
  processing_error: "Lỗi xử lý",
  warming_up: "Đang khởi động",
  stale: "Dữ liệu quá hạn",
  missing: "Chưa nhận dữ liệu",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      message = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

function formatAge(ageMs) {
  if (ageMs == null) return "Chưa có";
  if (ageMs < 1000) return `${ageMs} ms`;
  if (ageMs < 60_000) return `${(ageMs / 1000).toFixed(1)} giây`;
  return `${Math.floor(ageMs / 60_000)} phút`;
}

function formatDate(value) {
  if (!value) return "Chưa có";
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    day: "2-digit", month: "2-digit", year: "numeric",
  }).format(new Date(value));
}

function badge(state, stale = false) {
  const effective = stale ? "stale" : (state || "unknown");
  const label = stale ? "QUÁ HẠN" : (stateLabels[effective] || effective.toUpperCase());
  return `<span class="state-badge ${escapeHtml(effective)}">${escapeHtml(label)}</span>`;
}

function showToast(message, error = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = `toast show${error ? " error" : ""}`;
  clearTimeout(ui.toastTimer);
  ui.toastTimer = setTimeout(() => { toast.className = "toast"; }, 3200);
}

function setServiceOnline(online) {
  $("#service-status").textContent = online ? "Đang hoạt động" : "Mất kết nối";
  $(".pulse").classList.toggle("online", online);
}

async function refreshDashboard(manual = false) {
  if (ui.polling) return;
  ui.polling = true;
  if (manual) $("#refresh-button").disabled = true;
  try {
    ui.dashboard = await request("/api/dashboard");
    renderDashboard();
    setServiceOnline(true);
    $("#last-update").textContent = new Date().toLocaleTimeString("vi-VN");
  } catch (error) {
    setServiceOnline(false);
    if (manual) showToast(`Không thể làm mới: ${error.message}`, true);
  } finally {
    ui.polling = false;
    $("#refresh-button").disabled = false;
  }
}

function renderDashboard() {
  const { health, sources, cameras, decision, outbound } = ui.dashboard;
  const freshCameras = cameras.filter((camera) => !camera.stale && ["pass", "blocked"].includes(camera.state)).length;
  const connectedSources = sources.filter((source) => source.connected).length;
  const expectedSources = new Set(cameras.map((camera) => camera.source_id)).size;

  const decisionCard = $("#decision-card");
  decisionCard.className = `summary-card decision-card ${decision.state}`;
  $("#decision-icon").textContent = decision.state === "pass" ? "✓" : decision.state === "blocked" ? "!" : "?";
  $("#decision-state").textContent = stateLabels[decision.state];
  $("#decision-subtitle").textContent = decision.state === "pass"
    ? "Mọi đoạn đều dưới ngưỡng chiếm dụng"
    : decision.state === "blocked"
      ? `${decision.blocked_areas.length} vị trí đang bị chặn`
      : `${decision.unavailable_cameras.length} camera chưa sẵn sàng`;
  $("#source-count").textContent = `${connectedSources} / ${expectedSources}`;
  $("#message-count").textContent = `${health.received_messages.toLocaleString("vi-VN")} message đã nhận`;
  $("#camera-count").textContent = `${freshCameras} / ${health.configured_cameras}`;
  $("#camera-subtitle").textContent = freshCameras === health.configured_cameras ? "Dữ liệu đầy đủ" : "Có camera thiếu hoặc quá hạn";
  $("#outbound-state").textContent = !outbound.enabled ? "ĐÃ TẮT" : outbound.connected ? "ĐÃ KẾT NỐI" : "ĐANG THỬ LẠI";
  $("#outbound-subtitle").textContent = outbound.enabled
    ? `${outbound.sent_messages.toLocaleString("vi-VN")} message đã gửi`
    : "Chưa bật outbound";
  $("#occupancy-threshold-chip").textContent = `Ngưỡng ${(decision.occupancy_threshold_ratio * 100).toFixed(0)}%`;

  renderCameras(cameras);
  renderDecision(decision);
  renderSources(sources);
  renderTransport();
}

function renderCameras(cameras) {
  const body = $("#camera-table-body");
  if (!cameras.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty-cell">Chưa cấu hình camera</td></tr>';
    return;
  }
  body.innerHTML = cameras.map((camera) => {
    const zones = camera.blocked_zones?.length ? camera.blocked_zones.join(", ") : "—";
    const occupancy = camera.maximum_occupancy_ratio == null
      ? "—"
      : `<div class="metric"><strong>${(camera.maximum_occupancy_ratio * 100).toFixed(1)}</strong><small>%</small></div>`;
    const worstZone = camera.zones?.reduce((current, zone) =>
      !current || zone.occupancy_ratio > current.occupancy_ratio ? zone : current, null);
    const widthDetail = worstZone
      ? `Chiếm ${worstZone.occupied_width_cm} cm · trống ${worstZone.free_width_cm} cm`
      : "";
    return `<tr>
      <td><div class="location-cell"><span class="order-dot">${camera.order}</span><div><span class="primary-text">${escapeHtml(camera.location_name)}</span><span class="secondary-text">Vị trí ${camera.order}</span></div></div></td>
      <td><span class="primary-text">${escapeHtml(camera.camera_name || camera.camera_id)}</span><span class="secondary-text">${escapeHtml(camera.camera_id)} · ${escapeHtml(camera.source_id)}</span></td>
      <td>${badge(camera.state, camera.stale)}</td>
      <td>${occupancy}<span class="secondary-text">${escapeHtml(widthDetail)}</span></td>
      <td><span class="metric">${escapeHtml(zones)}</span></td>
      <td><span class="primary-text">${formatAge(camera.age_ms)}</span><span class="secondary-text">${camera.occupancy_threshold_ratio == null ? "" : `Ngưỡng ${(camera.occupancy_threshold_ratio * 100).toFixed(0)}%`}</span></td>
    </tr>`;
  }).join("");
}

function renderDecision(decision) {
  $("#corridor-name").textContent = decision.corridor_name;
  const decisionBadge = $("#decision-badge");
  decisionBadge.className = `state-badge ${decision.state}`;
  decisionBadge.textContent = stateLabels[decision.state];
  $("#route-track").className = `route-track ${decision.state}`;

  const details = [
    ["Corridor ID", decision.corridor_id, false],
    ["Ngưỡng chiếm dụng", `${(decision.occupancy_threshold_ratio * 100).toFixed(0)}%`, false],
    ["Thời điểm quyết định", formatDate(decision.decided_at), false],
  ];
  decision.blocked_areas.forEach((area) => {
    details.push([
      area.location_name,
      `${reasonLabels[area.reason] || area.reason} · ${(area.maximum_occupancy_ratio * 100).toFixed(1)}%`,
      true,
    ]);
  });
  decision.unavailable_cameras.forEach((camera) => {
    details.push([
      camera.location_name,
      reasonLabels[camera.reason] || camera.reason,
      true,
    ]);
  });
  $("#decision-details").innerHTML = details.map(([label, value, alert]) =>
    `<div class="detail-row${alert ? " alert" : ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`
  ).join("");
}

function renderSources(sources) {
  const container = $("#source-list");
  if (!sources.length) {
    container.innerHTML = '<div class="empty-state">Chưa có Jetson kết nối</div>';
    return;
  }
  container.innerHTML = sources.map((source) => `<div class="source-row">
    <span class="source-dot ${source.connected ? "connected" : ""}"></span>
    <div><strong>${escapeHtml(source.source_id)}</strong><small>${source.connected ? "WebSocket đang mở" : "Đã ngắt kết nối"}${source.stale ? " · dữ liệu quá hạn" : ""}</small></div>
    <div class="source-meta"><strong>${source.message_count.toLocaleString("vi-VN")}</strong><small>${formatAge(source.age_ms)}</small></div>
  </div>`).join("");
}

function renderTransport() {
  const latest = ui.dashboard.latest_received || [];
  const select = $("#source-select");
  if (!latest.some((item) => item.payload.camera_id === ui.selectedSource)) {
    ui.selectedSource = latest[0]?.payload.camera_id || "";
  }
  select.innerHTML = latest.length
    ? latest.map((item) => `<option value="${escapeHtml(item.payload.camera_id)}"${item.payload.camera_id === ui.selectedSource ? " selected" : ""}>${escapeHtml(item.source_id)} · ${escapeHtml(item.payload.camera_name)}</option>`).join("")
    : '<option value="">Chưa có camera</option>';

  const receiving = ui.jsonTab === "received";
  $("#received-toolbar").classList.toggle("hidden", !receiving);
  let payload = null;
  if (receiving) {
    payload = latest.find((item) => item.payload.camera_id === ui.selectedSource) || null;
  } else {
    payload = ui.dashboard.outbound.last_payload;
  }
  $("#json-view").textContent = payload ? JSON.stringify(payload, null, 2) : "Chưa có dữ liệu.";
}

async function loadConfig() {
  try {
    ui.config = await request("/api/config");
    populateConfigForm();
  } catch (error) {
    showToast(`Không thể tải cấu hình: ${error.message}`, true);
  }
}

function populateConfigForm() {
  const config = ui.config;
  $("#corridor-id").value = config.corridor.corridor_id;
  $("#corridor-name-input").value = config.corridor.corridor_name;
  $("#maximum-occupancy").value = config.corridor.maximum_occupancy_ratio;
  $("#outbound-enabled").checked = config.outbound.enabled;
  $("#outbound-url").value = config.outbound.websocket_url || "";
  $("#reconnect-seconds").value = config.outbound.reconnect_seconds;
  const list = $("#camera-config-list");
  list.innerHTML = "";
  config.cameras.sort((a, b) => a.order - b.order).forEach(addCameraRow);
  updateCameraOrders();
}

function addCameraRow(camera = {}) {
  const fragment = $("#camera-row-template").content.cloneNode(true);
  const row = $(".camera-config-row", fragment);
  $("[data-field='camera_id']", row).value = camera.camera_id || "";
  $("[data-field='source_id']", row).value = camera.source_id || "";
  $("[data-field='location_name']", row).value = camera.location_name || "";
  $("#camera-config-list").appendChild(fragment);
  updateCameraOrders();
}

function updateCameraOrders() {
  $$(".camera-config-row", $("#camera-config-list")).forEach((row, index) => {
    $(".order-number", row).textContent = index + 1;
    $("[data-action='up']", row).disabled = index === 0;
    $("[data-action='down']", row).disabled = index === $$(".camera-config-row", $("#camera-config-list")).length - 1;
  });
}

function collectConfig() {
  const cameras = $$(".camera-config-row", $("#camera-config-list")).map((row, index) => ({
    camera_id: $("[data-field='camera_id']", row).value.trim(),
    source_id: $("[data-field='source_id']", row).value.trim(),
    order: index + 1,
    location_name: $("[data-field='location_name']", row).value.trim(),
  }));
  return {
    schema_version: 1,
    corridor: {
      corridor_id: $("#corridor-id").value.trim(),
      corridor_name: $("#corridor-name-input").value.trim(),
      maximum_occupancy_ratio: Number($("#maximum-occupancy").value),
    },
    cameras,
    outbound: {
      enabled: $("#outbound-enabled").checked,
      websocket_url: $("#outbound-url").value.trim() || null,
      reconnect_seconds: Number($("#reconnect-seconds").value),
    },
  };
}

async function saveConfig(event) {
  event.preventDefault();
  const form = $("#config-form");
  if (!form.reportValidity()) return;
  if (!$("#camera-config-list").children.length) {
    showToast("Cần ít nhất một camera.", true);
    return;
  }
  const button = $("#save-config");
  button.disabled = true;
  button.classList.add("loading");
  try {
    ui.config = await request("/api/config", {
      method: "PUT",
      body: JSON.stringify(collectConfig()),
    });
    populateConfigForm();
    await refreshDashboard();
    showToast("Đã lưu và áp dụng cấu hình mới.");
  } catch (error) {
    showToast(`Không thể lưu: ${error.message}`, true);
  } finally {
    button.disabled = false;
    button.classList.remove("loading");
  }
}

function switchView(view) {
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $$(".view").forEach((section) => section.classList.toggle("active", section.id === `${view}-view`));
  $("#page-eyebrow").textContent = view === "status" ? "GIÁM SÁT THỜI GIAN THỰC" : "THIẾT LẬP HỆ THỐNG";
  $("#page-title").textContent = view === "status" ? "Trạng thái hành lang" : "Cấu hình Aggregator";
}

function bindEvents() {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  $("#refresh-button").addEventListener("click", () => refreshDashboard(true));
  $("#config-form").addEventListener("submit", saveConfig);
  $("#add-camera").addEventListener("click", () => addCameraRow());
  $("#source-select").addEventListener("change", (event) => { ui.selectedSource = event.target.value; renderTransport(); });
  $$("[data-json-tab]").forEach((button) => button.addEventListener("click", () => {
    ui.jsonTab = button.dataset.jsonTab;
    $$("[data-json-tab]").forEach((item) => item.classList.toggle("active", item === button));
    renderTransport();
  }));
  $("#camera-config-list").addEventListener("click", (event) => {
    const action = event.target.closest("[data-action]")?.dataset.action;
    const row = event.target.closest(".camera-config-row");
    if (!action || !row) return;
    if (action === "remove") row.remove();
    if (action === "up" && row.previousElementSibling) row.parentElement.insertBefore(row, row.previousElementSibling);
    if (action === "down" && row.nextElementSibling) row.nextElementSibling.after(row);
    updateCameraOrders();
  });
}

async function initialize() {
  bindEvents();
  await Promise.all([loadConfig(), refreshDashboard()]);
  setInterval(() => { if (!document.hidden) refreshDashboard(); }, 1000);
}

initialize();
