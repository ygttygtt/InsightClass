const COLORS = { phone_use: '#ef4444', talking: '#3b82f6', sleeping: '#eab308' };
const DISPLAY_NAMES = window.DISPLAY_NAMES || {};
const DEFAULT_MODEL = window.DEFAULT_MODEL || '';

const state = {
  source: 'rtsp',
  selectedCamera: null,
  stream: null,
  detecting: false,
  detectTimer: null,
  lastResults: [],
  uploadResults: null,
  uploadFps: 30,
  frameCount: 0,
  animId: null,
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
  els.canvas.classList.remove('hidden');
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

function selectCamera(el, cam) {
  $$('.camera-item').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  state.selectedCamera = cam;
}

// ---- Camera CRUD ----
async function addCamera(data) {
  const res = await fetch('/api/cameras', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const result = await res.json();
  if (!res.ok) throw new Error(result.error || 'Failed');
  await loadCameras();
  return result;
}

async function deleteCamera(ip) {
  if (!confirm(`确认删除摄像头 ${ip}？`)) return;
  try {
    await fetch(`/api/cameras/${ip}`, { method: 'DELETE' });
    if (state.selectedCamera && state.selectedCamera.ip === ip) {
      state.selectedCamera = null;
    }
    await loadCameras();
  } catch (e) {
    alert('删除失败: ' + e.message);
  }
}

// ---- Camera Connectivity Test ----
async function testCameraConnectivity() {
  const btn = $('#btn-test-cameras');
  btn.disabled = true;
  btn.style.animation = 'spin .7s linear infinite';
  try {
    const cameras = state.cameras || [];
    const res = await fetch('/api/cameras/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cameras }),
    });
    const results = await res.json();
    const items = $$('.camera-item');
    items.forEach(item => {
      const ip = item.dataset.ip;
      const statusEl = item.querySelector('.cam-status');
      if (statusEl && results[ip]) {
        statusEl.className = 'cam-status ' + results[ip];
      }
    });
    if (state.cameras) {
      state.cameras.forEach(cam => {
        if (results[cam.ip]) cam._status = results[cam.ip];
      });
    }
  } catch (e) {
    console.error('Camera test error:', e);
  } finally {
    btn.disabled = false;
    btn.style.animation = '';
  }
}

// ---- Camera Form ----
function showCameraForm() {
  const wrapper = $('#cam-form-wrapper');
  wrapper.classList.remove('hidden');
  $('#cam-form-title').textContent = '添加摄像头';
  $('#cam-ip').value = '';
  $('#cam-ip').disabled = false;
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
  try {
    await addCamera({
      ip,
      username: $('#cam-username').value.trim() || undefined,
      password: $('#cam-password').value.trim() || undefined,
      port: parseInt($('#cam-port').value) || undefined,
      note: $('#cam-note').value.trim(),
    });
    hideCameraForm();
  } catch (e) {
    alert('保存失败: ' + e.message);
  }
}

// ---- RTSP Detection ----
function drawOverlay(cvsW, cvsH) {
  els.ctx.fillStyle = '#ef4444';
  els.ctx.beginPath();
  els.ctx.arc(20, 20, 5, 0, Math.PI * 2);
  els.ctx.fill();
  els.ctx.fillStyle = '#fff';
  els.ctx.font = '500 11px "JetBrains Mono", monospace';
  els.ctx.fillText('LIVE', 30, 24);
  if (state.selectedCamera) {
    els.ctx.fillStyle = 'rgba(255,255,255,.5)';
    els.ctx.font = '400 11px "JetBrains Mono", monospace';
    els.ctx.fillText(state.selectedCamera.ip, 20, cvsH - 12);
  }
}
async function detectRtspOnce() {
  if (!state.selectedCamera) return null;
  const fd = new FormData();
  fd.append('rtsp_url', state.selectedCamera.rtsp_url);
  fd.append('model', getModelPath());
  fd.append('confidence', getConfidence());
  fd.append('iou', getIou());
  const res = await fetch('/api/detect/rtsp', { method: 'POST', body: fd });
  return await res.json();
}

async function startRtspLoop() {
  if (state.detecting) return;
  state.detecting = true;
  els.btnStart.disabled = true;
  els.btnStop.disabled = false;

  hidePlaceholder();
  resetStats();

  const rtspUrl = state.selectedCamera.rtsp_url;

  // Start MJPEG stream in the <img> element — browser handles decoding natively
  els.image.classList.remove('hidden');
  els.image.src = '/api/stream/rtsp?rtsp_url=' + encodeURIComponent(rtspUrl);

  // Wait for the stream to start delivering frames
  await new Promise((resolve) => {
    els.image.onload = resolve;
    els.image.onerror = resolve;
    setTimeout(resolve, 2000);
  });

  // Set canvas to match rendered size
  const wrap = els.canvas.parentElement;
  els.canvas.width = wrap.clientWidth;
  els.canvas.height = wrap.clientHeight;

  // Poll for detections separately (lightweight, no base64 overhead)
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

      // Draw detection overlay on canvas
      const cvsW = els.canvas.width, cvsH = els.canvas.height;
      els.ctx.clearRect(0, 0, cvsW, cvsH);

      if (data.frame_width > 0 && data.frame_height > 0 && state.lastResults.length > 0) {
        // Match the img's object-fit: contain scaling
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

    // Show image on canvas
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      hidePlaceholder();
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

// ---- Video Detection ----
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
    const data = await res.json();

    state.uploadResults = data;
    state.uploadFps = data.fps || 30;
    state.mode = 'upload';
    resetStats();

    const url = URL.createObjectURL(file);
    els.video.src = url;
    els.video.classList.remove('hidden');
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
  state.detecting = false;
  if (state.detectTimer) { clearTimeout(state.detectTimer); state.detectTimer = null; }
  if (state.animId) { cancelAnimationFrame(state.animId); state.animId = null; }
  if (state.stream) {
    state.stream.getTracks().forEach(t => t.stop());
    state.stream = null;
  }
  // Stop MJPEG stream
  fetch('/api/stream/stop', { method: 'POST' }).catch(() => {});
  els.video.srcObject = null;
  els.video.src = '';
  els.video.classList.add('hidden');
  els.video.ontimeupdate = null;
  els.image.src = '';
  els.image.classList.add('hidden');
  state.uploadResults = null;
  state.mode = null;
  els.btnStart.disabled = false;
  els.btnStop.disabled = true;
  window.removeEventListener('resize', resizeCanvas);
}

// ---- Event Listeners ----
$$('.source-btn').forEach(btn => {
  btn.addEventListener('click', () => switchSource(btn.dataset.source));
});

els.btnStart.addEventListener('click', () => {
  if (state.source === 'rtsp') startRtspLoop();
  else if (state.source === 'webcam') startWebcam();
});

els.btnStop.addEventListener('click', () => {
  stopAll();
  showPlaceholder();
  resetStats();
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
