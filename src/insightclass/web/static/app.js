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
    const cameras = await res.json();
    const list = $('#camera-list');
    list.innerHTML = '';
    cameras.forEach((cam, i) => {
      const div = document.createElement('div');
      div.className = 'camera-item' + (i === 0 ? ' active' : '');
      div.dataset.url = cam.rtsp_url;
      div.dataset.ip = cam.ip;
      div.innerHTML = `<span class="cam-dot"></span><span class="cam-ip">${cam.ip}</span><span class="cam-group">${cam.group_label}</span>`;
      div.addEventListener('click', () => selectCamera(div, cam));
      list.appendChild(div);
    });
    if (cameras.length > 0) {
      state.selectedCamera = cameras[0];
    }
  } catch (e) {
    $('#camera-list').innerHTML = '<div class="camera-loading">加载失败</div>';
  }
}

function selectCamera(el, cam) {
  $$('.camera-item').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  state.selectedCamera = cam;
}

// ---- RTSP Detection ----
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
  resizeCanvas();
  resetStats();

  // Create a placeholder image for the canvas (RTSP has no local video element)
  // We'll draw detection results on a black background
  const placeholderImg = new Image();
  placeholderImg.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

  async function loop() {
    if (!state.detecting) return;
    try {
      const data = await detectRtspOnce();
      if (!data) return;
      state.lastResults = data.detections || [];

      // Draw on canvas
      const cvsW = els.canvas.width, cvsH = els.canvas.height;
      els.ctx.fillStyle = '#000';
      els.ctx.fillRect(0, 0, cvsW, cvsH);

      if (data.frame_width > 0 && data.frame_height > 0) {
        const scale = Math.min(cvsW / data.frame_width, cvsH / data.frame_height);
        const dw = data.frame_width * scale, dh = data.frame_height * scale;
        const dx = (cvsW - dw) / 2, dy = (cvsH - dh) / 2;

        if (state.lastResults.length > 0) {
          els.ctx.save();
          els.ctx.translate(dx, dy);
          drawDetections(state.lastResults, dw / data.frame_width, dh / data.frame_height);
          els.ctx.restore();
        }

        // Draw "LIVE" indicator
        els.ctx.fillStyle = '#ef4444';
        els.ctx.beginPath();
        els.ctx.arc(20, 20, 5, 0, Math.PI * 2);
        els.ctx.fill();
        els.ctx.fillStyle = '#fff';
        els.ctx.font = '500 11px "JetBrains Mono", monospace';
        els.ctx.fillText('LIVE', 30, 24);

        // Draw camera IP
        els.ctx.fillStyle = 'rgba(255,255,255,.5)';
        els.ctx.font = '400 11px "JetBrains Mono", monospace';
        els.ctx.fillText(state.selectedCamera.ip, 20, cvsH - 12);
      }

      updateStats(state.lastResults, data.latency_ms);
    } catch (e) {
      console.error('RTSP detection error:', e);
    }
    if (state.detecting) {
      state.detectTimer = setTimeout(loop, 100);
    }
  }
  loop();
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
  els.video.srcObject = null;
  els.video.src = '';
  els.video.classList.add('hidden');
  els.video.ontimeupdate = null;
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

// ---- Init ----
loadCameras();
if (!DEFAULT_MODEL) console.warn('No trained models found in experiments/');
