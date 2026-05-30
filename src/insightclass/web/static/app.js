const COLORS = {
  phone_use: '#ef4444',
  talking: '#3b82f6',
  sleeping: '#eab308',
  standing: '#22c55e',
};

const DISPLAY_NAMES = window.DISPLAY_NAMES || {};
const DEFAULT_MODEL = window.DEFAULT_MODEL || '';

const state = {
  mode: 'camera',
  stream: null,
  detecting: false,
  detectTimer: null,
  lastResults: [],      // current frame detections for camera mode
  uploadResults: null,  // all frames for upload mode
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
  canvas: $('#overlay-canvas'),
  ctx: $('#overlay-canvas').getContext('2d'),
  placeholder: $('#placeholder'),
  loading: $('#loading'),
  loadingText: $('#loading-text'),
  tabs: $$('.tab'),
  tabCamera: $('#tab-camera'),
  tabUpload: $('#tab-upload'),
  btnStart: $('#btn-start-camera'),
  btnStop: $('#btn-stop-camera'),
  btnUpload: $('#btn-upload'),
  fileInput: $('#file-input'),
};

// ---- Utility ----
function getModelPath() {
  return els.modelSelect.value || DEFAULT_MODEL;
}

function getConfidence() {
  return parseFloat(els.confidence.value);
}

function getIou() {
  return parseFloat(els.iou.value);
}

// ---- Stats ----
function resetStats() {
  state.frameCount = 0;
  state.lastResults = [];
  $('#frame-count').textContent = '0';
  $('#latency').textContent = '-- ms';
  for (const el of $$('.stat-count')) el.textContent = '0';
}

function updateStats(detections, latencyMs) {
  state.frameCount++;
  $('#frame-count').textContent = state.frameCount;
  if (latencyMs !== undefined) {
    $('#latency').textContent = latencyMs.toFixed(0) + ' ms';
  }
  const counts = {};
  for (const d of detections) {
    counts[d.class_name] = (counts[d.class_name] || 0) + 1;
  }
  for (const [cls, cnt] of Object.entries(counts)) {
    const el = $(`#count-${cls}`);
    if (el) el.textContent = cnt;
  }
}

// ---- Canvas drawing ----
function drawDetections(detections, canvasW, canvasH, scaleX, scaleY) {
  const ctx = els.ctx;
  for (const d of detections) {
    const [x1, y1, x2, y2] = d.xyxy;
    const rx1 = x1 * scaleX;
    const ry1 = y1 * scaleY;
    const rx2 = x2 * scaleX;
    const ry2 = y2 * scaleY;
    const w = rx2 - rx1;
    const h = ry2 - ry1;
    const color = COLORS[d.class_name] || '#888';

    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(2, Math.min(w, h) * 0.04);
    ctx.strokeRect(rx1, ry1, w, h);

    const label = `${d.display_name || d.class_name} ${(d.confidence * 100).toFixed(0)}%`;
    ctx.font = `${Math.max(12, h * 0.18)}px -apple-system, sans-serif`;
    const tm = ctx.measureText(label);
    const th = Math.max(14, h * 0.16);
    ctx.fillStyle = color;
    ctx.fillRect(rx1, ry1 - th - 2, tm.width + 6, th + 4);
    ctx.fillStyle = '#fff';
    ctx.fillText(label, rx1 + 3, ry1 - 4);
  }
}

function resizeCanvas() {
  const rect = els.canvas.parentElement.getBoundingClientRect();
  els.canvas.width = rect.width;
  els.canvas.height = rect.height;
}

// ---- Camera mode ----
async function startCamera() {
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 960 }, height: { ideal: 540 } } });
    els.video.srcObject = state.stream;
    els.video.classList.remove('hidden');
    els.canvas.classList.remove('hidden');
    els.placeholder.classList.add('hidden');
    await els.video.play();

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    state.detecting = true;
    els.btnStart.disabled = true;
    els.btnStop.disabled = false;
    resetStats();

    // Detection loop: send frames to backend
    async function sendFrame() {
      if (!state.detecting) return;
      try {
        const offCvs = document.createElement('canvas');
        offCvs.width = els.video.videoWidth;
        offCvs.height = els.video.videoHeight;
        const offCtx = offCvs.getContext('2d');
        offCtx.drawImage(els.video, 0, 0, offCvs.width, offCvs.height);
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
        console.error('Frame detection error:', e);
      }
    }

    state.detectTimer = setInterval(sendFrame, 200);

    // Draw loop: render video + detections continuously
    function drawLoop() {
      if (!state.detecting) return;
      const cvsW = els.canvas.width;
      const cvsH = els.canvas.height;
      const vw = els.video.videoWidth;
      const vh = els.video.videoHeight;

      // Fit video in canvas (contain)
      const scale = Math.min(cvsW / vw, cvsH / vh);
      const dw = vw * scale;
      const dh = vh * scale;
      const dx = (cvsW - dw) / 2;
      const dy = (cvsH - dh) / 2;

      els.ctx.clearRect(0, 0, cvsW, cvsH);
      els.ctx.drawImage(els.video, dx, dy, dw, dh);

      if (state.lastResults.length > 0) {
        const scaleX = dw / vw;
        const scaleY = dh / vh;
        els.ctx.save();
        els.ctx.translate(dx, dy);
        drawDetections(state.lastResults, cvsW, cvsH, scaleX, scaleY);
        els.ctx.restore();
      }

      state.animId = requestAnimationFrame(drawLoop);
    }
    state.animId = requestAnimationFrame(drawLoop);

  } catch (e) {
    console.error('Camera error:', e);
    alert('无法打开摄像头: ' + e.message);
  }
}

function stopCamera() {
  state.detecting = false;
  if (state.detectTimer) { clearInterval(state.detectTimer); state.detectTimer = null; }
  if (state.animId) { cancelAnimationFrame(state.animId); state.animId = null; }
  if (state.stream) {
    state.stream.getTracks().forEach(t => t.stop());
    state.stream = null;
  }
  els.video.srcObject = null;
  els.video.classList.add('hidden');
  els.canvas.classList.add('hidden');
  els.placeholder.classList.remove('hidden');
  els.btnStart.disabled = false;
  els.btnStop.disabled = true;
  els.ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
  window.removeEventListener('resize', resizeCanvas);
}

// ---- Video upload mode ----
async function uploadVideo() {
  const file = els.fileInput.files[0];
  if (!file) { alert('请先选择视频文件'); return; }

  els.loading.classList.remove('hidden');
  els.loadingText.textContent = '正在上传并分析视频...';
  els.btnUpload.disabled = true;

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

    // Set up video playback
    const url = URL.createObjectURL(file);
    els.video.src = url;
    els.video.classList.remove('hidden');
    els.canvas.classList.remove('hidden');
    els.placeholder.classList.add('hidden');
    els.loading.classList.add('hidden');
    els.btnUpload.disabled = false;

    resizeCanvas();

    // Sync detection overlay with playback
    els.video.ontimeupdate = function () {
      if (state.mode !== 'upload' || !state.uploadResults) return;
      const currentTime = els.video.currentTime;
      const frameIdx = Math.round(currentTime * state.uploadFps);
      const frameData = state.uploadResults.frames[frameIdx] || null;

      const cvsW = els.canvas.width;
      const cvsH = els.canvas.height;
      const vw = state.uploadResults.video_width || els.video.videoWidth;
      const vh = state.uploadResults.video_height || els.video.videoHeight;

      const scale = Math.min(cvsW / vw, cvsH / vh);
      const dw = vw * scale;
      const dh = vh * scale;
      const dx = (cvsW - dw) / 2;
      const dy = (cvsH - dh) / 2;

      els.ctx.clearRect(0, 0, cvsW, cvsH);
      els.ctx.drawImage(els.video, dx, dy, dw, dh);

      if (frameData && frameData.detections.length > 0) {
        const scaleX = dw / vw;
        const scaleY = dh / vh;
        els.ctx.save();
        els.ctx.translate(dx, dy);
        drawDetections(frameData.detections, cvsW, cvsH, scaleX, scaleY);
        els.ctx.restore();
      }

      if (frameData) {
        updateStats(frameData.detections, undefined);
      }
    };

    els.video.play();

  } catch (e) {
    console.error('Upload error:', e);
    alert('视频分析失败: ' + e.message);
    els.loading.classList.add('hidden');
    els.btnUpload.disabled = false;
  }
}

// ---- Tab switching ----
function switchTab(mode) {
  state.mode = mode;
  if (mode === 'camera') {
    stopCamera();
    els.tabCamera.classList.remove('hidden');
    els.tabUpload.classList.add('hidden');
  } else {
    if (state.stream) stopCamera();
    els.video.classList.add('hidden');
    els.canvas.classList.add('hidden');
    els.placeholder.classList.remove('hidden');
    els.tabCamera.classList.add('hidden');
    els.tabUpload.classList.remove('hidden');
    els.ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
  }
  resetStats();
}

els.tabs.forEach(t => {
  t.addEventListener('click', () => {
    els.tabs.forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    switchTab(t.dataset.tab);
  });
});

// ---- Event listeners ----
els.btnStart.addEventListener('click', startCamera);
els.btnStop.addEventListener('click', stopCamera);
els.btnUpload.addEventListener('click', uploadVideo);

els.confidence.addEventListener('input', () => {
  els.confVal.textContent = els.confidence.value;
});
els.iou.addEventListener('input', () => {
  els.iouVal.textContent = els.iou.value;
});

// ---- Init ----
if (!DEFAULT_MODEL) {
  console.warn('No trained models found in experiments/');
}
