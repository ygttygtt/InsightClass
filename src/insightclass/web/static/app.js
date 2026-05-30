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
  // Playback modal
  playbackAnimId: null,
  playbackResults: null,
  playbackFps: 30,
  playbackPlaying: false,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const esc = (s) => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };

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
  btnDetectVideo: $('#btn-detect-video'),
  imageInput: $('#image-input'),
  videoInput: $('#video-input'),
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
function drawDetections(detections, scaleX, scaleY) {
  const ctx = els.ctx;
  for (const d of detections) {
    const [x1, y1, x2, y2] = d.xyxy;
    const rx1 = x1 * scaleX, ry1 = y1 * scaleY;
    const rx2 = x2 * scaleX, ry2 = y2 * scaleY;
    const w = rx2 - rx1, h = ry2 - ry1;
    const color = COLORS[d.class_name] || '#888';

    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(2, Math.min(w, h) * 0.035);
    ctx.strokeRect(rx1, ry1, w, h);

    const label = `${d.display_name || d.class_name} ${(d.confidence * 100).toFixed(0)}%`;
    ctx.font = `500 ${Math.max(11, h * 0.16)}px 'Noto Sans SC', sans-serif`;
    const tm = ctx.measureText(label);
    const th = Math.max(14, h * 0.15);
    ctx.fillStyle = color;
    const pad = 4;
    ctx.beginPath();
    ctx.roundRect(rx1, ry1 - th - pad * 2, tm.width + pad * 2, th + pad * 2, 3);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.fillText(label, rx1 + pad, ry1 - pad - 1);
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
  state.source = source;
  els.sourceLabel.textContent = SOURCE_LABELS[source] || source;

  $$('.source-btn').forEach(b => b.classList.toggle('active', b.dataset.source === source));
  $$('.source-panel').forEach(p => p.classList.toggle('active', p.id === `panel-${source}`));

  const showStart = source === 'rtsp' || source === 'webcam';
  els.btnStart.style.display = showStart ? '' : 'none';
  els.btnStop.style.display = showStart ? '' : 'none';

  showPlaceholder();
  resetStats();
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
  cameras.forEach((cam, i) => {
    const div = document.createElement('div');
    div.className = 'camera-item' + (i === 0 ? ' active' : '') + (cam.custom ? ' custom' : '');
    div.dataset.url = cam.rtsp_url;
    div.dataset.ip = cam.ip;
    const statusClass = cam._status || 'unknown';
    const noteSpan = cam.note ? `<span class="cam-note" title="${esc(cam.note)}">${esc(cam.note)}</span>` : '';
    const deleteBtn = cam.custom ? `<button class="cam-delete" data-ip="${esc(cam.ip)}" title="删除">&times;</button>` : '';
    div.innerHTML = `<span class="cam-dot"></span><span class="cam-ip">${esc(cam.ip)}</span>${noteSpan}<span class="cam-group">${esc(cam.group_label)}</span><span class="cam-status ${esc(statusClass)}"></span>${deleteBtn}`;
    div.addEventListener('click', (e) => {
      if (e.target.classList.contains('cam-delete')) return;
      selectCamera(div, cam);
    });
    const delBtn = div.querySelector('.cam-delete');
    if (delBtn) {
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteCamera(cam.ip);
      });
    }
    list.appendChild(div);
  });
  if (cameras.length > 0 && !state.selectedCamera) {
    state.selectedCamera = cameras[0];
  }
}

// ---- Camera Selection → Immediate Monitor ----
function selectCamera(el, cam) {
  $$('.camera-item').forEach(c => c.classList.remove('active'));
  el.classList.add('active');

  // If switching to a different camera, restart the stream immediately
  const changed = !state.selectedCamera || state.selectedCamera.ip !== cam.ip;
  state.selectedCamera = cam;

  if (state.source === 'rtsp' && changed) {
    stopDetection();
    startMonitor();
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

// ---- Image Detection ----
async function detectImage() {
  const file = els.imageInput.files[0];
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

// ---- Video Detection (single) ----
async function detectVideo() {
  const file = els.videoInput.files[0];
  if (!file) return;

  els.loading.classList.remove('hidden');
  els.loadingText.textContent = '正在上传并分析视频...';
  els.btnDetectVideo.disabled = true;

  try {
    const fd = new FormData();
    fd.append('video', file);
    fd.append('model', getModelPath());
    fd.append('confidence', getConfidence());
    fd.append('iou', getIou());

    const res = await fetch('/api/detect/upload', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`服务器返回 ${res.status}`);
    const data = await res.json();

    state.uploadResults = data;
    state.uploadFps = data.fps || 30;
    state.mode = 'upload';
    resetStats();

    const url = URL.createObjectURL(file);
    els.video.src = url;
    els.video.classList.remove('hidden');
    els.image.classList.add('hidden');
    hidePlaceholder();
    els.loading.classList.add('hidden');
    els.btnDetectVideo.disabled = false;
    resizeCanvas();

    let drawPending = false;
    els.video.ontimeupdate = function () {
      if (drawPending) return;
      drawPending = true;
      requestAnimationFrame(() => {
        drawPending = false;
        if (state.mode !== 'upload' || !state.uploadResults) return;
        const frameIdx = Math.round(els.video.currentTime * state.uploadFps);
        if (frameIdx < 0 || frameIdx >= state.uploadResults.frames.length) return;
        const frameData = state.uploadResults.frames[frameIdx];
        drawFrame(els.video, frameData.detections);
        updateStats(frameData.detections, undefined);
      });
    };
    els.video.play();
  } catch (e) {
    console.error('Video detection error:', e);
    alert('视频分析失败: ' + e.message);
    els.loading.classList.add('hidden');
    els.btnDetectVideo.disabled = false;
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
  els.video.srcObject = null;
  els.video.src = '';
  els.video.classList.add('hidden');
  els.video.ontimeupdate = null;
  els.image.src = '';
  els.image.classList.add('hidden');
  state.uploadResults = null;
  state.mode = null;
  window.removeEventListener('resize', resizeCanvas);
}

// ============================================================
// ---- Batch Video Detection ----
// ============================================================

function batchAddFiles(files) {
  for (const f of files) {
    if (f.type.startsWith('video/')) {
      state.batchFiles.push(f);
    }
  }
  renderBatchQueue();
}

function batchRemoveFile(index) {
  state.batchFiles.splice(index, 1);
  renderBatchQueue();
}

function renderBatchQueue() {
  const queue = $('#batch-queue');
  const list = $('#batch-queue-list');
  const countEl = $('#batch-queue-count');
  const btnDetect = $('#btn-batch-detect');
  const exportRow = $('#batch-export-row');

  if (state.batchFiles.length === 0 && !state.batchId) {
    queue.classList.add('hidden');
    return;
  }
  queue.classList.remove('hidden');

  // Use server items if batch has been submitted, otherwise local files
  const hasResults = state.batchId && state.batchItems.length > 0;

  if (hasResults) {
    countEl.textContent = state.batchItems.length;
    list.innerHTML = '';
    state.batchItems.forEach((item, i) => {
      const div = document.createElement('div');
      div.className = 'batch-item';

      let statusHtml = `<span class="batch-item-status ${esc(item.status)}">${statusLabel(item.status)}</span>`;
      let rightHtml = '';

      if (item.status === 'processing') {
        rightHtml = `<div class="batch-item-progress"><div class="batch-item-progress-bar" style="width: 50%"></div></div>`;
      } else if (item.status === 'done') {
        const counts = buildBatchCountsHtml(item.detection_summary);
        rightHtml = `<span class="batch-item-summary">${counts}</span>`;
        rightHtml += `<button class="batch-item-view" data-index="${i}" title="查看结果">查看</button>`;
      } else if (item.status === 'error') {
        rightHtml = `<span class="batch-item-summary" title="${esc(item.error)}">失败</span>`;
      }

      div.innerHTML = `<span class="batch-item-name" title="${esc(item.filename)}">${esc(item.filename)}</span>${statusHtml}${rightHtml}`;
      list.appendChild(div);
    });

    // Wire up view buttons
    list.querySelectorAll('.batch-item-view').forEach(btn => {
      btn.addEventListener('click', () => openPlaybackModal(parseInt(btn.dataset.index)));
    });

    // Show export if any items are done
    const anyDone = state.batchItems.some(it => it.status === 'done');
    exportRow.classList.toggle('hidden', !anyDone);
    btnDetect.disabled = true;
    btnDetect.textContent = state.batchProcessing ? '检测中...' : '批量检测';
  } else {
    countEl.textContent = state.batchFiles.length;
    list.innerHTML = '';
    state.batchFiles.forEach((f, i) => {
      const div = document.createElement('div');
      div.className = 'batch-item';
      div.innerHTML = `<span class="batch-item-name" title="${esc(f.name)}">${esc(f.name)}</span><span class="batch-item-status pending">待处理</span><button class="batch-item-remove" data-index="${i}" title="移除">&times;</button>`;
      list.appendChild(div);
    });
    list.querySelectorAll('.batch-item-remove').forEach(btn => {
      btn.addEventListener('click', () => batchRemoveFile(parseInt(btn.dataset.index)));
    });
    btnDetect.disabled = state.batchFiles.length === 0 || state.batchProcessing;
    btnDetect.textContent = '批量检测';
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

  const loading = els.loading;
  const loadingText = els.loadingText;
  loading.classList.remove('hidden');

  try {
    // Step 1: Upload all files
    loadingText.textContent = `正在上传 ${state.batchFiles.length} 个视频...`;
    const fd = new FormData();
    state.batchFiles.forEach(f => fd.append('videos', f));
    const uploadRes = await fetch('/api/detect/batch-upload', { method: 'POST', body: fd });
    if (!uploadRes.ok) throw new Error(`上传失败: ${uploadRes.status}`);
    const uploadData = await uploadRes.json();
    state.batchId = uploadData.batch_id;

    // Step 2: Start detection
    loadingText.textContent = '正在批量检测...';
    const detectFd = new FormData();
    detectFd.append('model', getModelPath());
    detectFd.append('confidence', getConfidence());
    detectFd.append('iou', getIou());
    const detectRes = await fetch(`/api/detect/batch/${state.batchId}`, { method: 'POST', body: detectFd });
    if (!detectRes.ok) throw new Error(`检测失败: ${detectRes.status}`);
    const resultData = await detectRes.json();

    state.batchItems = resultData.items || [];
    loading.classList.add('hidden');
  } catch (e) {
    console.error('Batch detection error:', e);
    alert('批量检测失败: ' + e.message);
    loading.classList.add('hidden');
  }

  state.batchProcessing = false;
  renderBatchQueue();
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
          drawPlaybackDetections(ctx, dets, dw / vw, dh / vh);
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

function drawPlaybackDetections(ctx, detections, scaleX, scaleY) {
  for (const d of detections) {
    const [x1, y1, x2, y2] = d.xyxy;
    const rx1 = x1 * scaleX, ry1 = y1 * scaleY;
    const rx2 = x2 * scaleX, ry2 = y2 * scaleY;
    const w = rx2 - rx1, h = ry2 - ry1;
    const color = COLORS[d.class_name] || '#888';

    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(2, Math.min(w, h) * 0.035);
    ctx.strokeRect(rx1, ry1, w, h);

    const label = `${d.display_name || d.class_name} ${(d.confidence * 100).toFixed(0)}%`;
    ctx.font = `500 ${Math.max(11, h * 0.16)}px 'Noto Sans SC', sans-serif`;
    const tm = ctx.measureText(label);
    const th = Math.max(14, h * 0.15);
    ctx.fillStyle = color;
    const pad = 4;
    ctx.beginPath();
    ctx.roundRect(rx1, ry1 - th - pad * 2, tm.width + pad * 2, th + pad * 2, 3);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.fillText(label, rx1 + pad, ry1 - pad - 1);
  }
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
els.btnDetectVideo.addEventListener('click', detectVideo);

els.imageInput.addEventListener('change', () => {
  els.btnDetectImage.disabled = !els.imageInput.files[0];
});
els.videoInput.addEventListener('change', () => {
  els.btnDetectVideo.disabled = !els.videoInput.files[0];
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

// ---- Batch Drag & Drop ----
const batchZone = document.getElementById('video-batch-drop');
if (batchZone) {
  batchZone.addEventListener('dragover', e => { e.preventDefault(); batchZone.style.borderColor = 'var(--accent)'; });
  batchZone.addEventListener('dragleave', () => { batchZone.style.borderColor = ''; });
  batchZone.addEventListener('drop', e => {
    e.preventDefault();
    batchZone.style.borderColor = '';
    if (e.dataTransfer.files.length > 0) {
      batchAddFiles(e.dataTransfer.files);
    }
  });
}

// ---- Batch Events ----
const batchInput = $('#video-batch-input');
if (batchInput) {
  batchInput.addEventListener('change', () => {
    if (batchInput.files.length > 0) {
      batchAddFiles(batchInput.files);
      batchInput.value = '';
    }
  });
}

const btnBatchDetect = $('#btn-batch-detect');
if (btnBatchDetect) {
  btnBatchDetect.addEventListener('click', batchDetect);
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
function showCameraForm() {
  $('#cam-form-wrapper').classList.remove('hidden');
  $('#cam-ip').value = '';
  $('#cam-username').value = '';
  $('#cam-password').value = '';
  $('#cam-port').value = '554';
  $('#cam-note').value = '';
  $('#cam-ip').focus();
}

function hideCameraForm() {
  $('#cam-form-wrapper').classList.add('hidden');
}

async function saveCameraForm() {
  const ip = $('#cam-ip').value.trim();
  if (!ip) { alert('请输入 IP 地址'); return; }
  const body = {
    ip,
    username: $('#cam-username').value.trim() || 'admin',
    password: $('#cam-password').value.trim() || '',
    port: parseInt($('#cam-port').value) || 554,
    note: $('#cam-note').value.trim(),
  };
  try {
    const res = await fetch('/api/cameras', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json();
      alert(err.error || '保存失败');
      return;
    }
    hideCameraForm();
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

async function testCameraConnectivity() {
  const btn = $('#btn-test-cameras');
  btn.disabled = true;
  btn.style.opacity = '0.5';
  try {
    const res = await fetch('/api/cameras/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const results = await res.json();
    $$('.camera-item').forEach(el => {
      const ip = el.dataset.ip;
      const dot = el.querySelector('.cam-status');
      if (dot && results[ip]) {
        dot.className = 'cam-status ' + results[ip];
      }
    });
  } catch (e) {
    console.error('Connectivity test failed:', e);
  }
  btn.disabled = false;
  btn.style.opacity = '';
}

// ---- Camera Management Events ----
$('#btn-add-camera').addEventListener('click', showCameraForm);
$('#btn-test-cameras').addEventListener('click', testCameraConnectivity);
$('#cam-form-close').addEventListener('click', hideCameraForm);
$('#cam-form-cancel').addEventListener('click', hideCameraForm);
$('#cam-form-save').addEventListener('click', saveCameraForm);
$('#cam-form-wrapper').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') saveCameraForm();
  if (e.key === 'Escape') hideCameraForm();
});

// ---- Init ----
loadCameras();
if (!DEFAULT_MODEL) console.warn('No trained models found in experiments/');
