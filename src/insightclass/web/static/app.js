const COLORS = { phone_use: '#ef4444', talking: '#3b82f6', sleeping: '#eab308' };
const DISPLAY_NAMES = window.DISPLAY_NAMES || {};
const DEFAULT_MODEL = window.DEFAULT_MODEL || '';

const state = {
  source: 'rtsp',
  selectedCamera: null,
  stream: null,           // getUserMedia stream (webcam)
  streaming: false,       // MJPEG stream active (RTSP monitor)
  detecting: false,       // inference active
  detectTimer: null,
  lastResults: [],
  uploadResults: null,
  uploadFps: 30,
  frameCount: 0,
  animId: null,
  // Batch video detection
  batchFiles: [],         // Array of File objects
  batchId: null,
  batchItems: [],         // Server-side batch item results
  batchProcessing: false,
  videoBlobUrl: null,    // Current video blob URL for streaming detection
  // Playback modal
  playbackAnimId: null,
  playbackResults: null,
  playbackFps: 30,
  playbackPlaying: false,
  // File list
  fileList: [],
  activeFileId: null,
  filePanelOpen: false,
  filePanelTab: 'image',
  selectionMode: false,
};

let _fileIdCounter = 0;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const esc = (s) => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };
const escAttr = (s) => esc(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// ---- Elements ----
const els = {
  modelSelect: $('#model-select'),
  confidence: $('#confidence'),
  confVal: $('#conf-val'),
  iou: $('#iou'),
  iouVal: $('#iou-val'),
  video: $('#source-video'),
  image: $('#source-image'),
  canvas: $('#overlay-canvas'),
  ctx: $('#overlay-canvas').getContext('2d'),
  placeholder: $('#placeholder'),
  loading: $('#loading'),
  loadingText: $('#loading-text'),
  sourceLabel: $('#source-label'),
  btnStart: $('#btn-start'),
  btnStop: $('#btn-stop'),
  btnDetectImage: $('#btn-detect-image'),
  imageInput: $('#image-input'),
  videoInput: $('#video-input'),
  btnFileList: $('#btn-file-list'),
  fileCountBadge: $('#file-count-badge'),
  filePanel: $('#file-panel'),
  filePanelBody: $('#file-panel-body'),
  filePanelCount: $('#file-panel-count'),
  filePanelClose: $('#file-panel-close'),
  filePanelOverlay: $('#file-panel-overlay'),
  btnExportSelected: $('#btn-export-selected'),
  exportSelectedCount: $('#export-selected-count'),
  fileSelectAll: $('#file-select-all'),
  fileExportProgress: $('#file-export-progress'),
  fileExportBarFill: $('#file-export-bar-fill'),
  fileExportText: $('#file-export-text'),
  btnSelectMode: $('#btn-select-mode'),
  btnClearFiles: $('#btn-clear-files'),
};

// ---- Utility ----
function getModelPath() { return els.modelSelect.value || DEFAULT_MODEL; }
function getConfidence() { return parseFloat(els.confidence.value); }
function getIou() { return parseFloat(els.iou.value); }

function formatTime(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return m + ':' + String(s).padStart(2, '0');
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ---- Stats ----
function resetStats() {
  state.frameCount = 0;
  state.lastResults = [];
  $('#frame-count').textContent = '0';
  $('#latency').textContent = '--';
  for (const el of $$('.stat-num')) el.textContent = '0';
}

function updateStats(detections, latencyMs) {
  state.frameCount++;
  $('#frame-count').textContent = state.frameCount;
  if (latencyMs !== undefined) $('#latency').textContent = latencyMs.toFixed(0) + ' ms';
  const counts = {};
  for (const d of detections) counts[d.class_name] = (counts[d.class_name] || 0) + 1;
  for (const [cls, cnt] of Object.entries(counts)) {
    const el = $(`#count-${cls}`);
    if (el) el.textContent = cnt;
  }
}

// ---- Canvas Drawing ----
function drawDetections(detections, scaleX, scaleY, ctx) {
  ctx = ctx || els.ctx;
  const LINE_W = 2;
  const FONT_SIZE = 12;
  const FONT = `600 ${FONT_SIZE}px 'Noto Sans SC', sans-serif`;
  const PAD = 4;
  const LABEL_H = FONT_SIZE + PAD * 2;

  for (const d of detections) {
    const [x1, y1, x2, y2] = d.xyxy;
    const rx1 = x1 * scaleX, ry1 = y1 * scaleY;
    const rx2 = x2 * scaleX, ry2 = y2 * scaleY;
    const w = rx2 - rx1, h = ry2 - ry1;
    const color = COLORS[d.class_name] || '#888';

    ctx.strokeStyle = color;
    ctx.lineWidth = LINE_W;
    ctx.strokeRect(rx1, ry1, w, h);

    const label = `${d.display_name || d.class_name} ${(d.confidence * 100).toFixed(0)}%`;
    ctx.font = FONT;
    const tm = ctx.measureText(label);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(rx1, ry1 - LABEL_H - PAD, tm.width + PAD * 2, LABEL_H + PAD, 3);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.fillText(label, rx1 + PAD, ry1 - PAD - 1);
  }
}

function drawFrame(sourceEl, detections) {
  const cvsW = els.canvas.width, cvsH = els.canvas.height;
  const vw = sourceEl.videoWidth || sourceEl.naturalWidth || sourceEl.width;
  const vh = sourceEl.videoHeight || sourceEl.naturalHeight || sourceEl.height;
  if (!vw || !vh) return;

  const scale = Math.min(cvsW / vw, cvsH / vh);
  const dw = vw * scale, dh = vh * scale;
  const dx = (cvsW - dw) / 2, dy = (cvsH - dh) / 2;

  els.ctx.clearRect(0, 0, cvsW, cvsH);
  els.ctx.drawImage(sourceEl, dx, dy, dw, dh);

  if (detections && detections.length > 0) {
    els.ctx.save();
    els.ctx.translate(dx, dy);
    drawDetections(detections, dw / vw, dh / vh);
    els.ctx.restore();
  }
}

function resizeCanvas() {
  const rect = els.canvas.parentElement.getBoundingClientRect();
  els.canvas.width = rect.width;
  els.canvas.height = rect.height;
}

// ---- Source Switching ----
const SOURCE_LABELS = { rtsp: 'RTSP 监控', webcam: '电脑摄像头', image: '图片检测', video: '视频检测' };

function switchSource(source) {
  stopAll();
  closeFilePanel();
  state.source = source;
  state.filePanelTab = source === 'video' ? 'video' : 'image';
  state.selectionMode = false;
  els.sourceLabel.textContent = SOURCE_LABELS[source] || source;

  $$('.source-btn').forEach(b => b.classList.toggle('active', b.dataset.source === source));
  $$('.source-panel').forEach(p => p.classList.toggle('active', p.id === `panel-${source}`));

  const showStart = source === 'rtsp' || source === 'webcam';
  els.btnStart.style.display = showStart ? '' : 'none';
  els.btnStop.style.display = showStart ? '' : 'none';
  els.btnFileList.style.display = showStart ? 'none' : '';

  // Right sidebar: only show in RTSP mode
  const rightSidebar = $('#right-sidebar');
  if (rightSidebar) rightSidebar.style.display = source === 'rtsp' ? '' : 'none';

  showPlaceholder();
  resetStats();
  updateExportButton();
  updateFileCountBadge();
}

function showPlaceholder() {
  els.video.classList.add('hidden');
  els.image.classList.add('hidden');
  els.canvas.classList.add('hidden');
  els.placeholder.classList.remove('hidden');
  els.ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
}

function hidePlaceholder() {
  els.placeholder.classList.add('hidden');
}

// ---- Camera List ----
async function loadCameras() {
  try {
    const res = await fetch('/api/cameras');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const cameras = await res.json();
    state.cameras = cameras;
    renderCameraList(cameras);

    // Auto-select camera from query param (e.g. /?camera=10.8.14.36)
    const params = new URLSearchParams(window.location.search);
    const targetIp = params.get('camera');
    if (targetIp) {
      const items = $$('.camera-item');
      items.forEach(el => {
        if (el.dataset.ip === targetIp) el.click();
      });
      return;
    }

    // Auto-select first camera on load (no auto connectivity test)
    if (state.source === 'rtsp') {
      const items = $$('.camera-item');
      if (items.length > 0) items[0].click();
    }
  } catch (e) {
    console.error('Camera list error:', e);
    $('#camera-list').innerHTML = '<div class="camera-loading">加载失败，请检查服务是否正常运行</div>';
  }
}

function renderCameraList(cameras) {
  const list = $('#camera-list');
  list.innerHTML = '';
  if (cameras.length === 0) {
    list.innerHTML = '<div class="camera-loading">暂无摄像头，点击 + 添加</div>';
    return;
  }

  // Group cameras by group field
  const groupOrder = ['front', 'rear', 'custom'];
  const groupLabelMap = {};
  const groups = {};
  cameras.forEach(cam => {
    const g = cam.group || 'custom';
    if (!groups[g]) {
      groups[g] = [];
      groupLabelMap[g] = cam.group_label || g;
    }
    groups[g].push(cam);
  });

  // Sort groups: front, rear, then custom, then any others
  const sortedGroups = Object.keys(groups).sort((a, b) => {
    const ai = groupOrder.indexOf(a), bi = groupOrder.indexOf(b);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  let firstItem = true;
  sortedGroups.forEach(groupKey => {
    const cams = groups[groupKey];
    const label = groupLabelMap[groupKey];
    const isCollapsed = groupKey === 'custom';

    // Group header
    const header = document.createElement('div');
    header.className = 'cam-group-header' + (isCollapsed ? ' collapsed' : '');
    header.dataset.group = groupKey;
    header.innerHTML = '<span class="cam-group-toggle">&#9660;</span><span class="cam-group-title">' + esc(label) + '</span><span class="cam-group-count">' + cams.length + '</span>';
    header.addEventListener('click', () => {
      header.classList.toggle('collapsed');
      const items = list.querySelector('.cam-group-items[data-group="' + groupKey + '"]');
      if (items) items.classList.toggle('collapsed');
    });
    list.appendChild(header);

    // Group items container
    const itemsDiv = document.createElement('div');
    itemsDiv.className = 'cam-group-items' + (isCollapsed ? ' collapsed' : '');
    itemsDiv.dataset.group = groupKey;

    cams.forEach(cam => {
      const div = document.createElement('div');
      div.className = 'camera-item' + (firstItem ? ' active' : '') + (cam.custom ? ' custom' : '');
      div.dataset.url = cam.rtsp_url;
      div.dataset.ip = cam.ip;
      const statusClass = cam._status || 'unknown';
      const noteSpan = cam.note ? '<span class="cam-note" title="' + escAttr(cam.note) + '">' + esc(cam.note) + '</span>' : '';
      const editBtn = '<button class="cam-edit" data-ip="' + esc(cam.ip) + '" title="编辑">&#9998;</button>';
      const deleteBtn = cam.custom ? '<button class="cam-delete" data-ip="' + esc(cam.ip) + '" title="删除">&times;</button>' : '';

      // Build name/ip display
      let infoHtml;
      if (cam.name) {
        infoHtml = '<div class="cam-info"><span class="cam-name">' + esc(cam.name) + '</span><span class="cam-ip">' + esc(cam.ip) + '</span></div>';
      } else {
        infoHtml = '<div class="cam-info"><span class="cam-ip-only">' + esc(cam.ip) + '</span></div>';
      }

      div.innerHTML = '<span class="cam-dot"></span>' + infoHtml + noteSpan + '<span class="cam-status ' + esc(statusClass) + '"></span>' + editBtn + deleteBtn;
      div.addEventListener('click', (e) => {
        if (e.target.classList.contains('cam-delete') || e.target.classList.contains('cam-edit')) return;
        selectCamera(div, cam);
      });
      const edBtn = div.querySelector('.cam-edit');
      if (edBtn) {
        edBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          openEditCamera(cam);
        });
      }
      const delBtn = div.querySelector('.cam-delete');
      if (delBtn) {
        delBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          deleteCamera(cam.ip);
        });
      }
      itemsDiv.appendChild(div);
      firstItem = false;
    });

    list.appendChild(itemsDiv);
  });

  if (cameras.length > 0 && !state.selectedCamera) {
    state.selectedCamera = cameras[0];
  }
}

// ---- Camera Selection → Immediate Monitor ----
function selectCamera(el, cam) {
  $$('.camera-item').forEach(c => c.classList.remove('active'));
  el.classList.add('active');

  // If switching to a different camera, restart the stream
  const changed = !state.selectedCamera || state.selectedCamera.ip !== cam.ip;
  const wasDetecting = state.detecting;
  state.selectedCamera = cam;

  if (state.source === 'rtsp' && changed) {
    stopDetection();
    startMonitor().then(() => {
      // If detection was ON, restart it after stream connects
      if (wasDetecting && state.streaming) {
        startDetection();
      }
    });
  }
}

// ---- RTSP Monitor (stream only, no detection) ----
async function startMonitor() {
  if (!state.selectedCamera) return;
  if (state.streaming) {
    // Stop current stream before starting new one
    fetch('/api/stream/stop', { method: 'POST' }).catch(() => {});
    state.streaming = false;
  }

  hidePlaceholder();
  els.loading.classList.remove('hidden');
  els.loadingText.textContent = '正在连接摄像头...';
  els.image.classList.remove('hidden');
  els.canvas.classList.remove('hidden');
  resizeCanvas();

  const rtspUrl = state.selectedCamera.rtsp_url;
  els.image.src = '/api/stream/rtsp?rtsp_url=' + encodeURIComponent(rtspUrl);

  // Poll stream status
  let connected = false;
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 500));
    try {
      const st = await fetch('/api/stream/status').then(r => r.json());
      if (st.status === 'streaming') { connected = true; break; }
      if (st.status === 'error') {
        els.loading.classList.add('hidden');
        els.image.classList.add('hidden');
        showPlaceholder();
        alert('摄像头连接失败: ' + (st.error || '未知错误'));
        return;
      }
    } catch (e) { /* ignore */ }
  }

  els.loading.classList.add('hidden');
  if (!connected) {
    els.image.classList.add('hidden');
    showPlaceholder();
    alert('摄像头连接超时，请检查网络和 IP 地址');
    return;
  }

  state.streaming = true;
}

// ---- RTSP Detection (overlay on existing stream) ----
function startDetection() {
  if (state.detecting) return;
  if (!state.streaming) return;

  state.detecting = true;
  els.btnStart.disabled = true;
  els.btnStop.disabled = false;
  resetStats();

  const cvsW = els.canvas.width, cvsH = els.canvas.height;
  const rtspUrl = state.selectedCamera.rtsp_url;

  async function detectLoop() {
    if (!state.detecting) return;
    try {
      const fd = new FormData();
      fd.append('rtsp_url', rtspUrl);
      fd.append('model', getModelPath());
      fd.append('confidence', getConfidence());
      fd.append('iou', getIou());
      const res = await fetch('/api/detect/rtsp', { method: 'POST', body: fd });
      const data = await res.json();
      state.lastResults = data.detections || [];

      // Redraw detection overlay
      els.ctx.clearRect(0, 0, cvsW, cvsH);
      if (data.frame_width > 0 && data.frame_height > 0 && state.lastResults.length > 0) {
        const imgAspect = data.frame_width / data.frame_height;
        const wrapAspect = cvsW / cvsH;
        let drawW, drawH, drawX, drawY;
        if (imgAspect > wrapAspect) {
          drawW = cvsW; drawH = cvsW / imgAspect; drawX = 0; drawY = (cvsH - drawH) / 2;
        } else {
          drawH = cvsH; drawW = cvsH * imgAspect; drawX = (cvsW - drawW) / 2; drawY = 0;
        }
        els.ctx.save();
        els.ctx.translate(drawX, drawY);
        drawDetections(state.lastResults, drawW / data.frame_width, drawH / data.frame_height);
        els.ctx.restore();
      }
      updateStats(state.lastResults, data.latency_ms);
    } catch (e) {
      console.error('Detection error:', e);
    }
    if (state.detecting) state.detectTimer = setTimeout(detectLoop, 300);
  }
  detectLoop();
}

function stopDetection() {
  state.detecting = false;
  if (state.detectTimer) { clearTimeout(state.detectTimer); state.detectTimer = null; }
  state.lastResults = [];
  els.ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
  els.btnStart.disabled = false;
  els.btnStop.disabled = true;
}

// ---- Webcam ----
async function startWebcam() {
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 960 }, height: { ideal: 540 } } });
    els.video.srcObject = state.stream;
    els.video.classList.remove('hidden');
    els.canvas.classList.remove('hidden');
    hidePlaceholder();
    await els.video.play();
    resizeCanvas();

    state.detecting = true;
    els.btnStart.disabled = true;
    els.btnStop.disabled = false;
    resetStats();

    async function sendFrame() {
      if (!state.detecting) return;
      try {
        const offCvs = document.createElement('canvas');
        offCvs.width = els.video.videoWidth;
        offCvs.height = els.video.videoHeight;
        offCvs.getContext('2d').drawImage(els.video, 0, 0, offCvs.width, offCvs.height);
        const blob = await new Promise(r => offCvs.toBlob(r, 'image/jpeg', 0.8));
        if (!blob || !state.detecting) return;

        const fd = new FormData();
        fd.append('image', blob, 'frame.jpg');
        fd.append('model', getModelPath());
        fd.append('confidence', getConfidence());
        fd.append('iou', getIou());

        const res = await fetch('/api/detect/frame', { method: 'POST', body: fd });
        const data = await res.json();
        state.lastResults = data.detections || [];
        updateStats(state.lastResults, data.latency_ms);
      } catch (e) {
        console.error('Webcam frame error:', e);
      }
      if (state.detecting) state.detectTimer = setTimeout(sendFrame, 50);
    }
    sendFrame();

    function drawLoop() {
      if (!state.detecting) return;
      drawFrame(els.video, state.lastResults);
      state.animId = requestAnimationFrame(drawLoop);
    }
    state.animId = requestAnimationFrame(drawLoop);
  } catch (e) {
    alert('无法打开摄像头: ' + e.message);
  }
}

// ---- Video Streaming Detection ----
function startVideoStream(file) {
  // Clean up any existing stream
  if (state.videoBlobUrl) {
    URL.revokeObjectURL(state.videoBlobUrl);
    state.videoBlobUrl = null;
  }
  stopDetection();
  if (state.animId) { cancelAnimationFrame(state.animId); state.animId = null; }

  // Create blob URL and set up video with native controls
  state.videoBlobUrl = URL.createObjectURL(file);
  els.video.src = state.videoBlobUrl;
  els.video.controls = true;
  els.video.playbackRate = 1.0;
  els.video.classList.remove('hidden');
  els.canvas.classList.remove('hidden');
  els.image.classList.add('hidden');
  hidePlaceholder();
  resizeCanvas();

  state.detecting = true;
  resetStats();

  // Detection loop (~500ms interval, captures current video frame)
  async function detectLoop() {
    if (!state.detecting) return;
    if (els.video.paused || els.video.ended || els.video.readyState < 2) {
      state.detectTimer = setTimeout(detectLoop, 200);
      return;
    }
    try {
      const offCvs = document.createElement('canvas');
      offCvs.width = els.video.videoWidth;
      offCvs.height = els.video.videoHeight;
      offCvs.getContext('2d').drawImage(els.video, 0, 0, offCvs.width, offCvs.height);
      const blob = await new Promise(r => offCvs.toBlob(r, 'image/jpeg', 0.8));
      if (!blob || !state.detecting) return;

      const fd = new FormData();
      fd.append('image', blob, 'frame.jpg');
      fd.append('model', getModelPath());
      fd.append('confidence', getConfidence());
      fd.append('iou', getIou());

      const res = await fetch('/api/detect/frame', { method: 'POST', body: fd });
      const data = await res.json();
      state.lastResults = data.detections || [];
      updateStats(state.lastResults, data.latency_ms);
    } catch (e) {
      console.error('Video stream frame error:', e);
    }
    if (state.detecting) state.detectTimer = setTimeout(detectLoop, 500);
  }
  detectLoop();

  // Draw loop — only overlay detections, video element handles its own display
  // Canvas has pointer-events:none so native video controls remain clickable
  function drawLoop() {
    if (!state.detecting) return;
    const cvsW = els.canvas.width, cvsH = els.canvas.height;
    const vw = els.video.videoWidth, vh = els.video.videoHeight;
    if (vw && vh) {
      const scale = Math.min(cvsW / vw, cvsH / vh);
      const dw = vw * scale, dh = vh * scale;
      const dx = (cvsW - dw) / 2, dy = (cvsH - dh) / 2;
      els.ctx.clearRect(0, 0, cvsW, cvsH);
      if (state.lastResults.length > 0) {
        els.ctx.save();
        els.ctx.translate(dx, dy);
        drawDetections(state.lastResults, dw / vw, dh / vh);
        els.ctx.restore();
      }
    }
    state.animId = requestAnimationFrame(drawLoop);
  }
  state.animId = requestAnimationFrame(drawLoop);
}

// ---- Image Detection ----
async function detectImage() {
  let file = null;
  if (state.activeFileId) {
    const entry = state.fileList.find(f => f.id === state.activeFileId);
    if (entry && entry.type === 'image') file = entry.file;
  }
  if (!file && els.imageInput.files[0]) file = els.imageInput.files[0];
  if (!file) return;

  els.loading.classList.remove('hidden');
  els.loadingText.textContent = '正在分析图片...';

  try {
    const fd = new FormData();
    fd.append('image', file);
    fd.append('model', getModelPath());
    fd.append('confidence', getConfidence());
    fd.append('iou', getIou());

    const res = await fetch('/api/detect/frame', { method: 'POST', body: fd });
    const data = await res.json();
    state.lastResults = data.detections || [];

    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      hidePlaceholder();
      els.image.classList.add('hidden');
      els.canvas.classList.remove('hidden');
      els.canvas.width = els.canvas.parentElement.clientWidth;
      els.canvas.height = els.canvas.parentElement.clientHeight;
      drawFrame(img, state.lastResults);
      updateStats(state.lastResults, data.latency_ms);
      els.loading.classList.add('hidden');
      URL.revokeObjectURL(url);
    };
    img.src = url;
  } catch (e) {
    console.error('Image detection error:', e);
    els.loading.classList.add('hidden');
  }
}

// ---- Stop ----
function stopAll() {
  stopDetection();
  state.streaming = false;
  if (state.animId) { cancelAnimationFrame(state.animId); state.animId = null; }
  if (state.stream) {
    state.stream.getTracks().forEach(t => t.stop());
    state.stream = null;
  }
  fetch('/api/stream/stop', { method: 'POST' }).catch(() => {});
  if (state.videoBlobUrl) {
    URL.revokeObjectURL(state.videoBlobUrl);
    state.videoBlobUrl = null;
  }
  els.video.srcObject = null;
  els.video.src = '';
  els.video.controls = false;
  els.video.classList.add('hidden');
  els.video.ontimeupdate = null;
  els.image.src = '';
  els.image.classList.add('hidden');
  state.uploadResults = null;
  state.mode = null;
  window.removeEventListener('resize', resizeCanvas);
}

// ============================================================
// ---- Unified Video Queue ----
// ============================================================

function batchAddFiles(files) {
  for (const f of files) {
    if (f.type.startsWith('video/')) {
      state.batchFiles.push(f);
    }
  }
  // Reset batch state when adding new files
  if (state.batchId) {
    state.batchId = null;
    state.batchItems = [];
  }
  renderBatchQueue();
}

function batchRemoveFile(index) {
  state.batchFiles.splice(index, 1);
  if (state.batchFiles.length === 0) {
    state.batchId = null;
    state.batchItems = [];
  }
  renderBatchQueue();
}

function updateExportButton() {
  const btn = $('#btn-export-video');
  if (!btn) return;
  if (state.batchProcessing) {
    const doneCount = (state.batchItems || []).filter(it => it.status === 'done' || it.status === 'error').length;
    const totalCount = (state.batchItems || []).length || state.batchFiles.length;
    btn.textContent = totalCount > 0 ? `导出中 ${doneCount}/${totalCount}...` : '导出中...';
    btn.disabled = true;
  } else if (state.batchId && state.batchItems && state.batchItems.length > 0) {
    const anyDone = state.batchItems.some(it => it.status === 'done');
    btn.textContent = anyDone ? '导出完成' : '导出标注视频';
    btn.disabled = false;
    const exportRow = $('#batch-export-row');
    if (exportRow) exportRow.classList.toggle('hidden', !anyDone);
  } else {
    btn.textContent = '导出标注视频';
    btn.disabled = state.batchFiles.length === 0;
  }
}

function renderBatchQueue() {
  updateExportButton();
  const queue = $('#batch-queue');
  if (!queue) return;
  const list = $('#batch-queue-list');
  const countEl = $('#batch-queue-count');
  const btnDetect = $('#btn-batch-detect');
  const exportRow = $('#batch-export-row');
  const totalProg = $('#batch-total-progress');
  const totalFill = $('#batch-total-bar-fill');
  const totalText = $('#batch-total-text');

  if (state.batchFiles.length === 0 && !state.batchId) {
    queue.classList.add('hidden');
    return;
  }
  queue.classList.remove('hidden');

  const hasResults = state.batchId && state.batchItems.length > 0;

  if (hasResults) {
    countEl.textContent = state.batchItems.length;
    list.innerHTML = '';

    // Total progress bar
    const doneCount = state.batchItems.filter(it => it.status === 'done' || it.status === 'error').length;
    const totalCount = state.batchItems.length;
    const pct = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

    if (state.batchProcessing) {
      totalProg.classList.remove('hidden');
      totalFill.style.width = pct + '%';
      totalText.textContent = `${doneCount} / ${totalCount} 已完成`;
    } else {
      totalProg.classList.add('hidden');
    }

    state.batchItems.forEach((item, i) => {
      const div = document.createElement('div');
      div.className = 'batch-item' + (item.status === 'processing' ? ' processing-current' : '');

      let statusHtml = `<span class="batch-item-status ${esc(item.status)}">${statusLabel(item.status)}</span>`;
      let rightHtml = '';

      if (item.status === 'processing') {
        rightHtml = `<div class="batch-item-progress"><div class="batch-item-progress-bar" style="width:60%"></div></div>`;
      } else if (item.status === 'done') {
        const counts = buildBatchCountsHtml(item.detection_summary);
        rightHtml = `<span class="batch-item-summary">${counts}</span>`;
        rightHtml += `<button class="batch-item-view" data-index="${i}" title="查看结果">查看</button>`;
      } else if (item.status === 'error') {
        rightHtml = `<span class="batch-item-summary" title="${escAttr(item.error)}">失败</span>`;
      }

      div.innerHTML = `<span class="batch-item-name" title="${escAttr(item.filename)}">${esc(item.filename)}</span>${statusHtml}${rightHtml}`;
      list.appendChild(div);
    });

    list.querySelectorAll('.batch-item-view').forEach(btn => {
      btn.addEventListener('click', () => openPlaybackModal(parseInt(btn.dataset.index)));
    });

    const anyDone = state.batchItems.some(it => it.status === 'done');
    exportRow.classList.toggle('hidden', !anyDone);
    btnDetect.disabled = state.batchProcessing;
    btnDetect.textContent = state.batchProcessing ? `检测中 ${doneCount}/${totalCount}...` : '重新检测';
  } else {
    // Show local files waiting to be submitted
    countEl.textContent = state.batchFiles.length;
    list.innerHTML = '';
    totalProg.classList.add('hidden');
    state.batchFiles.forEach((f, i) => {
      const div = document.createElement('div');
      div.className = 'batch-item';
      div.innerHTML = `<span class="batch-item-name" title="${escAttr(f.name)}">${esc(f.name)}</span><span class="batch-item-status pending">待处理</span><button class="batch-item-remove" data-index="${i}" title="移除">&times;</button>`;
      list.appendChild(div);
    });
    list.querySelectorAll('.batch-item-remove').forEach(btn => {
      btn.addEventListener('click', () => batchRemoveFile(parseInt(btn.dataset.index)));
    });
    btnDetect.disabled = state.batchFiles.length === 0 || state.batchProcessing;
    btnDetect.textContent = '开始检测';
    exportRow.classList.add('hidden');
  }
}

function statusLabel(status) {
  const map = { pending: '待处理', processing: '检测中', done: '已完成', error: '失败' };
  return map[status] || status;
}

function buildBatchCountsHtml(summary) {
  if (!summary || Object.keys(summary).length === 0) return '--';
  const parts = [];
  for (const [cls, cnt] of Object.entries(summary)) {
    const color = COLORS[cls] || '#888';
    const name = DISPLAY_NAMES[cls] || cls;
    parts.push(`<span class="batch-count-chip"><span class="batch-count-dot" style="background:${color}"></span>${name}:${cnt}</span>`);
  }
  return parts.join('');
}

async function batchDetect() {
  if (state.batchFiles.length === 0 || state.batchProcessing) return;
  state.batchProcessing = true;
  renderBatchQueue();

  try {
    // Step 1: Upload all files
    const fd = new FormData();
    state.batchFiles.forEach(f => fd.append('videos', f));
    const uploadRes = await fetch('/api/detect/batch-upload', { method: 'POST', body: fd });
    if (!uploadRes.ok) throw new Error(`上传失败: ${uploadRes.status}`);
    const uploadData = await uploadRes.json();
    state.batchId = uploadData.batch_id;

    // Initialize items as pending
    state.batchItems = state.batchFiles.map(f => ({
      filename: f.name, status: 'pending', detection_summary: {}, error: ''
    }));
    renderBatchQueue();

    // Step 2: Start detection (non-blocking)
    const detectFd = new FormData();
    detectFd.append('model', getModelPath());
    detectFd.append('confidence', getConfidence());
    detectFd.append('iou', getIou());
    fetch(`/api/detect/batch/${state.batchId}`, { method: 'POST', body: detectFd })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); })
      .catch(e => { console.error('Batch detect start failed:', e); });

    // Step 3: Poll for progress
    await batchPollProgress();
  } catch (e) {
    console.error('Batch detection error:', e);
    alert('批量检测失败: ' + e.message);
  }

  state.batchProcessing = false;
  renderBatchQueue();
}

async function batchPollProgress() {
  while (state.batchProcessing) {
    await new Promise(r => setTimeout(r, 1000));
    try {
      const res = await fetch(`/api/detect/batch/${state.batchId}`);
      if (!res.ok) continue;
      const data = await res.json();
      state.batchItems = data.items || [];
      renderBatchQueue();

      if (data.status === 'done') break;
    } catch (e) { /* ignore */ }
  }
}

async function batchExport(format) {
  if (!state.batchId) return;
  const url = `/api/detect/batch/${state.batchId}/export?format=${format}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = `batch_${state.batchId}_detections.${format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ============================================================
// ---- Playback Modal ----
// ============================================================

function openPlaybackModal(itemIndex) {
  const item = state.batchItems[itemIndex];
  if (!item || item.status !== 'done') return;

  const modal = $('#playback-modal');
  const video = $('#playback-video');
  const canvas = $('#playback-canvas');
  const title = $('#playback-title');
  const stats = $('#playback-stats');

  // Fetch full item detail (with frames data)
  fetch(`/api/detect/batch/${state.batchId}/item/${itemIndex}`)
    .then(r => r.json())
    .then(data => {
      state.playbackResults = data;
      state.playbackFps = data.fps || 30;

      title.textContent = data.filename;

      // Build stats
      stats.innerHTML = '';
      const summary = data.detection_summary || {};
      for (const [cls, cnt] of Object.entries(summary)) {
        const color = COLORS[cls] || '#888';
        const name = DISPLAY_NAMES[cls] || cls;
        const chip = document.createElement('div');
        chip.className = 'playback-stat-chip';
        chip.innerHTML = `<span class="playback-stat-dot" style="background:${color}"></span><span class="playback-stat-name">${esc(name)}</span><span class="playback-stat-num">${cnt}</span>`;
        stats.appendChild(chip);
      }

      // Use the original uploaded video file for playback
      // Find the matching file in batchFiles by filename
      const matchFile = state.batchFiles.find(f => f.name === data.filename);
      if (matchFile) {
        const blobUrl = URL.createObjectURL(matchFile);
        video.src = blobUrl;
      }

      modal.classList.remove('hidden');
      resizePlaybackCanvas();
    })
    .catch(e => {
      console.error('Failed to load item detail:', e);
      alert('加载结果失败');
    });
}

function closePlaybackModal() {
  const modal = $('#playback-modal');
  const video = $('#playback-video');
  modal.classList.add('hidden');
  video.pause();
  video.src = '';
  state.playbackResults = null;
  state.playbackPlaying = false;
  if (state.playbackAnimId) {
    cancelAnimationFrame(state.playbackAnimId);
    state.playbackAnimId = null;
  }
  // Revoke blob URL
  if (video.src && video.src.startsWith('blob:')) {
    URL.revokeObjectURL(video.src);
  }
}

function resizePlaybackCanvas() {
  const canvas = $('#playback-canvas');
  const viewer = canvas.parentElement;
  canvas.width = viewer.clientWidth;
  canvas.height = viewer.clientHeight;
}

function togglePlayback() {
  const video = $('#playback-video');
  if (video.paused) {
    video.play();
    state.playbackPlaying = true;
    $('#playback-play-btn').textContent = '暂停';
    startPlaybackLoop();
  } else {
    video.pause();
    state.playbackPlaying = false;
    $('#playback-play-btn').textContent = '播放';
    if (state.playbackAnimId) {
      cancelAnimationFrame(state.playbackAnimId);
      state.playbackAnimId = null;
    }
  }
}

function startPlaybackLoop() {
  const video = $('#playback-video');
  const canvas = $('#playback-canvas');
  const seekBar = $('#playback-seek');
  const timeDisplay = $('#playback-time');

  function loop() {
    if (!state.playbackResults || !state.playbackPlaying) return;

    const ctx = canvas.getContext('2d');
    const cvsW = canvas.width, cvsH = canvas.height;
    const vw = video.videoWidth, vh = video.videoHeight;

    if (vw && vh) {
      const scale = Math.min(cvsW / vw, cvsH / vh);
      const dw = vw * scale, dh = vh * scale;
      const dx = (cvsW - dw) / 2, dy = (cvsH - dh) / 2;

      ctx.clearRect(0, 0, cvsW, cvsH);
      ctx.drawImage(video, dx, dy, dw, dh);

      // Get detections for current frame
      const frameIdx = Math.round(video.currentTime * state.playbackFps);
      const frames = state.playbackResults.frames || [];
      if (frameIdx >= 0 && frameIdx < frames.length) {
        const dets = frames[frameIdx].detections || [];
        if (dets.length > 0) {
          ctx.save();
          ctx.translate(dx, dy);
          drawDetections(dets, dw / vw, dh / vh, ctx);
          ctx.restore();
        }
      }

      // Update seek bar
      if (video.duration) {
        seekBar.value = (video.currentTime / video.duration) * 100;
        timeDisplay.textContent = formatTime(video.currentTime) + ' / ' + formatTime(video.duration);
      }
    }

    state.playbackAnimId = requestAnimationFrame(loop);
  }
  state.playbackAnimId = requestAnimationFrame(loop);
}

// ============================================================
// ---- File List Panel ----
// ============================================================

async function generateThumbnail(file) {
  if (file.type.startsWith('image/')) {
    return URL.createObjectURL(file);
  }
  if (file.type.startsWith('video/')) {
    return new Promise((resolve) => {
      const video = document.createElement('video');
      video.preload = 'metadata';
      video.muted = true;
      video.src = URL.createObjectURL(file);
      video.onloadeddata = () => {
        video.currentTime = Math.min(1, video.duration * 0.1);
      };
      video.onseeked = () => {
        const canvas = document.createElement('canvas');
        canvas.width = 160;
        canvas.height = 90;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => {
          URL.revokeObjectURL(video.src);
          resolve(blob ? URL.createObjectURL(blob) : '');
        }, 'image/jpeg', 0.7);
      };
      video.onerror = () => {
        URL.revokeObjectURL(video.src);
        resolve('');
      };
    });
  }
  return '';
}

async function addFilesToList(fileInput) {
  const newEntries = [];
  for (const file of fileInput) {
    const type = file.type.startsWith('video/') ? 'video' : file.type.startsWith('image/') ? 'image' : null;
    if (!type) continue;
    const id = ++_fileIdCounter;
    const entry = { id, file, type, name: file.name, size: file.size, thumbnailUrl: '', status: 'pending', selected: false };
    state.fileList.push(entry);
    newEntries.push(entry);
  }
  // Generate thumbnails async
  for (const entry of newEntries) {
    generateThumbnail(entry.file).then(url => {
      entry.thumbnailUrl = url;
      renderFilePanel();
    });
  }
  updateFileCountBadge();
  // Auto-switch tab to match uploaded file types
  if (newEntries.length > 0) {
    const hasVideo = newEntries.some(e => e.type === 'video');
    const hasImage = newEntries.some(e => e.type === 'image');
    if (hasVideo && !hasImage) state.filePanelTab = 'video';
    else if (hasImage && !hasVideo) state.filePanelTab = 'image';
  }
  renderFilePanel();
  // Auto-open panel
  if (!state.filePanelOpen) toggleFilePanel();
  // Auto-preview first new file
  if (newEntries.length > 0) {
    previewFile(newEntries[0]);
  }
}

async function previewFile(entry) {
  // Stop any ongoing video playback / detection before switching
  if (state.detecting) { state.detecting = false; }
  if (state.detectTimer) { clearTimeout(state.detectTimer); state.detectTimer = null; }
  if (state.animId) { cancelAnimationFrame(state.animId); state.animId = null; }
  els.video.pause();
  if (state.videoBlobUrl) {
    URL.revokeObjectURL(state.videoBlobUrl);
    state.videoBlobUrl = null;
  }
  els.video.src = '';
  els.video.srcObject = null;
  els.video.controls = false;
  els.video.classList.add('hidden');
  state.lastResults = [];
  els.ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);

  state.activeFileId = entry.id;
  renderFilePanel();
  const file = entry.file;
  if (entry.type === 'image') {
    els.loading.classList.remove('hidden');
    els.loadingText.textContent = '正在分析图片...';
    try {
      const fd = new FormData();
      fd.append('image', file);
      fd.append('model', getModelPath());
      fd.append('confidence', getConfidence());
      fd.append('iou', getIou());
      const res = await fetch('/api/detect/frame', { method: 'POST', body: fd });
      const data = await res.json();
      state.lastResults = data.detections || [];
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        hidePlaceholder();
        els.video.classList.add('hidden');
        els.image.classList.add('hidden');
        els.canvas.classList.remove('hidden');
        els.canvas.width = els.canvas.parentElement.clientWidth;
        els.canvas.height = els.canvas.parentElement.clientHeight;
        drawFrame(img, state.lastResults);
        updateStats(state.lastResults, data.latency_ms);
        els.loading.classList.add('hidden');
        URL.revokeObjectURL(url);
      };
      img.src = url;
    } catch (e) {
      console.error('Image detection error:', e);
      els.loading.classList.add('hidden');
    }
  } else if (entry.type === 'video') {
    startVideoStream(file);
  }
}

function renderFilePanel() {
  const body = els.filePanelBody;
  const countEl = els.filePanelCount;

  // Update tab UI
  $$('.file-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === state.filePanelTab);
  });

  // Update select mode button
  if (els.btnSelectMode) {
    els.btnSelectMode.classList.toggle('active', state.selectionMode);
    els.btnSelectMode.title = state.selectionMode ? '退出选择' : '选择';
  }

  // Filter by current tab
  const filteredList = state.fileList.filter(f => f.type === state.filePanelTab);
  countEl.textContent = filteredList.length;

  if (filteredList.length === 0) {
    body.innerHTML = '<div class="file-panel-empty">暂无' + (state.filePanelTab === 'video' ? '视频' : '图片') + '文件</div>';
    updateExportSelectedBtn();
    return;
  }

  const statusLabels = { pending: '待处理', detecting: '检测中', done: '已完成', error: '失败' };
  let html = '<div class="file-grid">';
  for (const entry of filteredList) {
    const activeClass = entry.id === state.activeFileId ? ' active' : '';
    const thumbHtml = entry.thumbnailUrl
      ? `<img src="${esc(entry.thumbnailUrl)}" alt="">`
      : '<span class="file-thumb-placeholder">加载中...</span>';
    html += `<div class="file-card${activeClass}" data-id="${entry.id}">
      <div class="file-card-thumb">
        <input type="checkbox" class="file-card-checkbox" data-id="${entry.id}" ${entry.selected ? 'checked' : ''}>
        ${thumbHtml}
      </div>
      <button class="file-card-remove" data-id="${entry.id}" title="移除">&times;</button>
      <div class="file-card-info">
        <div class="file-card-name" title="${escAttr(entry.name)}">${esc(entry.name)}</div>
        <div class="file-card-meta">
          <span>${formatFileSize(entry.size)}</span>
          <span class="file-card-status ${entry.status}">${statusLabels[entry.status] || entry.status}</span>
        </div>
      </div>
    </div>`;
  }
  html += '</div>';
  body.innerHTML = html;

  // Bind click events
  body.querySelectorAll('.file-card').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.classList.contains('file-card-checkbox')) return;
      if (e.target.classList.contains('file-card-remove')) return;
      const id = parseInt(card.dataset.id);
      const entry = state.fileList.find(f => f.id === id);
      if (!entry) return;
      if (state.selectionMode) {
        entry.selected = !entry.selected;
        const cb = card.querySelector('.file-card-checkbox');
        if (cb) cb.checked = entry.selected;
        updateExportSelectedBtn();
      } else {
        previewFile(entry);
      }
    });
  });
  body.querySelectorAll('.file-card-checkbox').forEach(cb => {
    cb.addEventListener('change', (e) => {
      e.stopPropagation();
      const id = parseInt(cb.dataset.id);
      const entry = state.fileList.find(f => f.id === id);
      if (entry) entry.selected = cb.checked;
      updateExportSelectedBtn();
    });
  });
  body.querySelectorAll('.file-card-remove').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      removeFile(parseInt(btn.dataset.id));
    });
  });

  updateExportSelectedBtn();
}

function updateFileCountBadge() {
  const count = state.fileList.length;
  els.fileCountBadge.textContent = count;
  els.fileCountBadge.style.display = count > 0 ? '' : 'none';
}

function updateExportSelectedBtn() {
  const selectedCount = state.fileList.filter(f => f.selected).length;
  els.exportSelectedCount.textContent = selectedCount;
  els.btnExportSelected.disabled = selectedCount === 0;
}

function toggleFilePanel() {
  state.filePanelOpen = !state.filePanelOpen;
  els.filePanel.classList.toggle('open', state.filePanelOpen);
  els.filePanelOverlay.classList.toggle('hidden', !state.filePanelOpen);
  if (state.filePanelOpen) renderFilePanel();
}

function closeFilePanel() {
  state.filePanelOpen = false;
  els.filePanel.classList.remove('open');
  els.filePanelOverlay.classList.add('hidden');
}

function switchFileTab(tab) {
  state.filePanelTab = tab;
  renderFilePanel();
}

function toggleSelectionMode() {
  state.selectionMode = !state.selectionMode;
  renderFilePanel();
}

function clearAllFiles() {
  if (state.fileList.length === 0) return;
  if (!confirm('确定清空所有文件？')) return;
  // Revoke thumbnail URLs
  state.fileList.forEach(f => { if (f.thumbnailUrl) URL.revokeObjectURL(f.thumbnailUrl); });
  state.fileList = [];
  state.activeFileId = null;
  state.batchFiles = [];
  state.batchId = null;
  state.batchItems = [];
  updateFileCountBadge();
  renderFilePanel();
  showPlaceholder();
}

function removeFile(id) {
  const idx = state.fileList.findIndex(f => f.id === id);
  if (idx === -1) return;
  const entry = state.fileList[idx];
  if (entry.thumbnailUrl) URL.revokeObjectURL(entry.thumbnailUrl);
  // Remove from batchFiles if present
  const batchIdx = state.batchFiles.indexOf(entry.file);
  if (batchIdx !== -1) state.batchFiles.splice(batchIdx, 1);
  state.fileList.splice(idx, 1);
  if (state.activeFileId === id) state.activeFileId = null;
  updateFileCountBadge();
  renderFilePanel();
  if (state.fileList.length === 0) showPlaceholder();
}

async function exportSelected() {
  const selected = state.fileList.filter(f => f.selected);
  if (selected.length === 0) return;

  els.fileExportProgress.classList.remove('hidden');
  els.btnExportSelected.disabled = true;
  const results = [];

  for (let i = 0; i < selected.length; i++) {
    const entry = selected[i];
    entry.status = 'detecting';
    renderFilePanel();

    els.fileExportText.textContent = `正在处理 ${i + 1}/${selected.length}: ${entry.name}...`;
    els.fileExportBarFill.style.width = `${(i / selected.length) * 100}%`;

    try {
      if (entry.type === 'image') {
        const fd = new FormData();
        fd.append('image', entry.file);
        fd.append('model', getModelPath());
        fd.append('confidence', getConfidence());
        fd.append('iou', getIou());
        const res = await fetch('/api/detect/frame', { method: 'POST', body: fd });
        const data = await res.json();
        const dets = data.detections || [];
        results.push({ filename: entry.name, type: 'image', detections: dets });
        entry.status = 'done';
      } else {
        const fd = new FormData();
        fd.append('video', entry.file);
        fd.append('model', getModelPath());
        fd.append('confidence', getConfidence());
        fd.append('iou', getIou());
        const res = await fetch('/api/detect/upload', { method: 'POST', body: fd });
        const data = await res.json();
        const allDets = (data.frames || []).flatMap(f => f.detections || []);
        results.push({ filename: entry.name, type: 'video', frame_count: data.frame_count, detections: allDets });
        entry.status = 'done';
      }
    } catch (e) {
      entry.status = 'error';
      results.push({ filename: entry.name, type: entry.type, error: e.message, detections: [] });
    }
    renderFilePanel();
  }

  els.fileExportBarFill.style.width = '100%';
  els.fileExportText.textContent = '导出完成！正在下载...';

  downloadResults(results);
  updateExportSelectedBtn();

  setTimeout(() => {
    els.fileExportProgress.classList.add('hidden');
  }, 2000);
}

function downloadResults(results) {
  let csv = '\uFEFFfilename,type,class_name,display_name,confidence,x1,y1,x2,y2\n';
  for (const r of results) {
    for (const d of (r.detections || [])) {
      const x1 = d.xyxy[0].toFixed(1), y1 = d.xyxy[1].toFixed(1);
      const x2 = d.xyxy[2].toFixed(1), y2 = d.xyxy[3].toFixed(1);
      csv += `"${r.filename}",${r.type},${d.class_name},"${d.display_name || d.class_name}",${d.confidence},${x1},${y1},${x2},${y2}\n`;
    }
  }
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `detections_${new Date().toISOString().slice(0,10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---- Event Listeners ----
$$('.source-btn').forEach(btn => {
  btn.addEventListener('click', () => switchSource(btn.dataset.source));
});

els.btnStart.addEventListener('click', () => {
  if (state.source === 'rtsp') startDetection();
  else if (state.source === 'webcam') startWebcam();
});

els.btnStop.addEventListener('click', () => {
  if (state.source === 'rtsp') {
    stopDetection();
    resetStats();
  } else {
    stopAll();
    showPlaceholder();
    resetStats();
  }
});

els.btnDetectImage.addEventListener('click', detectImage);

els.imageInput.addEventListener('change', () => {
  if (els.imageInput.files.length > 0) {
    addFilesToList(els.imageInput.files);
    els.btnDetectImage.disabled = false;
    els.imageInput.value = '';
  }
});
els.videoInput.addEventListener('change', () => {
  if (els.videoInput.files.length > 0) {
    // Store files for batch export
    state.batchFiles = [];
    for (const f of els.videoInput.files) {
      if (f.type.startsWith('video/')) state.batchFiles.push(f);
    }
    if (state.batchId) { state.batchId = null; state.batchItems = []; }
    addFilesToList(els.videoInput.files);
    els.videoInput.value = '';
  }
});

els.confidence.addEventListener('input', () => {
  els.confVal.textContent = els.confidence.value;
});
els.iou.addEventListener('input', () => {
  els.iouVal.textContent = els.iou.value;
});

window.addEventListener('resize', resizeCanvas);

// ---- Drag & Drop ----
['image-drop', 'video-drop'].forEach(id => {
  const zone = document.getElementById(id);
  if (!zone) return;
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.style.borderColor = 'var(--accent)'; });
  zone.addEventListener('dragleave', () => { zone.style.borderColor = ''; });
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.style.borderColor = '';
    const input = zone.querySelector('input[type=file]');
    if (input && e.dataTransfer.files.length > 0) {
      input.files = e.dataTransfer.files;
      input.dispatchEvent(new Event('change'));
    }
  });
});

// ---- Batch Events ----

const btnExportVideo = $('#btn-export-video');
if (btnExportVideo) {
  btnExportVideo.addEventListener('click', batchDetect);
}

const btnExportCsv = $('#btn-export-csv');
if (btnExportCsv) {
  btnExportCsv.addEventListener('click', () => batchExport('csv'));
}

const btnExportJson = $('#btn-export-json');
if (btnExportJson) {
  btnExportJson.addEventListener('click', () => batchExport('json'));
}

// ---- Playback Modal Events ----
const playbackClose = $('#playback-close');
if (playbackClose) {
  playbackClose.addEventListener('click', closePlaybackModal);
}

const playbackModal = $('#playback-modal');
if (playbackModal) {
  playbackModal.addEventListener('click', (e) => {
    if (e.target === playbackModal) closePlaybackModal();
  });
}

const playbackPlayBtn = $('#playback-play-btn');
if (playbackPlayBtn) {
  playbackPlayBtn.addEventListener('click', togglePlayback);
}

const playbackSeek = $('#playback-seek');
if (playbackSeek) {
  playbackSeek.addEventListener('input', () => {
    const video = $('#playback-video');
    if (video.duration) {
      video.currentTime = (playbackSeek.value / 100) * video.duration;
    }
  });
}

const playbackVideo = $('#playback-video');
if (playbackVideo) {
  playbackVideo.addEventListener('ended', () => {
    state.playbackPlaying = false;
    $('#playback-play-btn').textContent = '播放';
  });
  playbackVideo.addEventListener('loadedmetadata', () => {
    resizePlaybackCanvas();
  });
}

window.addEventListener('resize', () => {
  if (!$('#playback-modal').classList.contains('hidden')) {
    resizePlaybackCanvas();
  }
});

// ---- Set Default Model ----
$('#btn-set-default').addEventListener('click', async () => {
  const model = getModelPath();
  if (!model) return;
  try {
    await fetch('/api/settings/default-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    });
    const btn = $('#btn-set-default');
    btn.classList.add('saved');
    setTimeout(() => btn.classList.remove('saved'), 1500);
  } catch (e) {
    console.error('Failed to save default model:', e);
  }
});

// ---- Camera Management ----
let _camEditIp = null; // null = add mode, string = edit mode
let _camEditDefault = false; // true if editing a default (non-custom) camera

async function openEditCamera(cam) {
  // For default cameras, we may not have credentials — fill with defaults
  showCameraModal(cam);
  _camEditDefault = !cam.custom;
}

function showCameraModal(cam) {
  const modal = $('#cam-modal');
  const title = $('#cam-modal-title');
  const ipInput = $('#cam-ip');
  if (cam) {
    _camEditIp = cam.ip;
    title.textContent = '编辑摄像头';
    ipInput.value = cam.ip;
    ipInput.disabled = true;
    ipInput.style.opacity = '0.5';
    $('#cam-name').value = cam.name || '';
    $('#cam-username').value = cam.username || 'admin';
    $('#cam-password').value = cam.password || '';
    $('#cam-port').value = cam.port || 554;
    $('#cam-note').value = cam.note || '';
  } else {
    _camEditIp = null;
    title.textContent = '添加摄像头';
    ipInput.value = '';
    ipInput.disabled = false;
    ipInput.style.opacity = '';
    $('#cam-name').value = '';
    $('#cam-username').value = '';
    $('#cam-password').value = '';
    $('#cam-port').value = '554';
    $('#cam-note').value = '';
  }
  modal.classList.remove('hidden');
  if (!cam) ipInput.focus();
}

function hideCameraModal() {
  $('#cam-modal').classList.add('hidden');
  _camEditIp = null;
  _camEditDefault = false;
}

async function saveCameraForm() {
  const ip = $('#cam-ip').value.trim();
  if (!ip) { alert('请输入 IP 地址'); return; }
  const body = {
    ip,
    name: $('#cam-name').value.trim(),
    username: $('#cam-username').value.trim() || 'admin',
    password: $('#cam-password').value.trim() || '',
    port: parseInt($('#cam-port').value) || 554,
    note: $('#cam-note').value.trim(),
  };
  try {
    let res;
    if (_camEditIp) {
      res = await fetch('/api/cameras/' + encodeURIComponent(_camEditIp), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } else {
      res = await fetch('/api/cameras', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    }
    if (!res.ok) {
      const err = await res.json();
      alert(err.error || '保存失败');
      return;
    }
    hideCameraModal();
    loadCameras();
  } catch (e) {
    alert('保存失败: ' + e.message);
  }
}

async function deleteCamera(ip) {
  if (!confirm(`确定删除摄像头 ${ip}？`)) return;
  try {
    await fetch(`/api/cameras/${ip}`, { method: 'DELETE' });
    loadCameras();
  } catch (e) {
    alert('删除失败: ' + e.message);
  }
}

let _testingConnectivity = false;

async function testCameraConnectivity() {
  if (_testingConnectivity) return;
  _testingConnectivity = true;

  const btn = $('#btn-test-cameras');
  btn.disabled = true;
  btn.style.opacity = '0.5';

  const items = $$('.camera-item');
  items.forEach(el => {
    const dot = el.querySelector('.cam-status');
    if (dot) dot.className = 'cam-status testing';
  });

  // Sequential: test one by one, update UI immediately as each completes
  for (const el of items) {
    const ip = el.dataset.ip;
    const dot = el.querySelector('.cam-status');
    if (!dot || !ip) continue;
    try {
      const res = await fetch(`/api/cameras/${ip}/test`);
      const data = await res.json();
      dot.className = 'cam-status ' + (data.status || 'disconnected');
    } catch (e) {
      dot.className = 'cam-status disconnected';
    }
  }

  btn.disabled = false;
  btn.style.opacity = '';
  _testingConnectivity = false;
}

// ---- Camera Management Events ----
$('#btn-add-camera').addEventListener('click', () => showCameraModal(null));
$('#btn-test-cameras').addEventListener('click', testCameraConnectivity);
$('#cam-modal-close').addEventListener('click', hideCameraModal);
$('#cam-form-cancel').addEventListener('click', hideCameraModal);
$('#cam-form-save').addEventListener('click', saveCameraForm);
$('#cam-modal .cam-modal-backdrop').addEventListener('click', hideCameraModal);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('#cam-modal').classList.contains('hidden')) {
    hideCameraModal();
  }
});
$('#cam-modal').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') saveCameraForm();
});

// ---- File Panel Events ----
els.btnFileList.addEventListener('click', toggleFilePanel);
els.filePanelClose.addEventListener('click', closeFilePanel);
els.filePanelOverlay.addEventListener('click', closeFilePanel);
els.btnExportSelected.addEventListener('click', exportSelected);
els.fileSelectAll.addEventListener('change', () => {
  const checked = els.fileSelectAll.checked;
  state.fileList.filter(f => f.type === state.filePanelTab).forEach(f => f.selected = checked);
  renderFilePanel();
});
$$('.file-tab').forEach(tab => {
  tab.addEventListener('click', () => switchFileTab(tab.dataset.tab));
});
els.btnSelectMode.addEventListener('click', toggleSelectionMode);
els.btnClearFiles.addEventListener('click', clearAllFiles);

// ---- Init ----
loadCameras();
if (!DEFAULT_MODEL) console.warn('No trained models found in experiments/');
