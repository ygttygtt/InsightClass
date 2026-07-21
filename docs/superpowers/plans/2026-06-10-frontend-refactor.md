# InsightClass Frontend Refactoring Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Jinja2+vanilla JS web frontend with a React+TypeScript SPA, merge 3 FastAPI apps into 1 pure REST API, and prepare for future Tauri desktop packaging.

**Architecture:** Single FastAPI server serves only REST endpoints (no HTML rendering). React SPA built with Vite, served as static files in production. During development, Vite dev server proxies API calls to FastAPI. Three pages remain: Detection (main), Dashboard, Experiments. Demo page is merged into Detection page.

**Tech Stack:** Python FastAPI (backend), React 18 + TypeScript + Vite (frontend), CSS Modules (styling), Chart.js (dashboard charts), React Router (routing).

---

## Decisions Made

- **Merge 3 FastAPI apps into 1** — `server.py`, `experiment_viewer.py`, `demo.py` become one `server.py` with all endpoints
- **Demo page removed** — image detection already exists in main page's Image mode; training results already exist in Experiments page
- **React + TypeScript** — chosen over Vue for ecosystem size and AI-assisted coding support
- **PyInstaller** for future Python sidecar packaging (Tauri phase, separate plan)

---

## Phase 1: Backend Consolidation

### Task 1: Merge experiment_viewer and demo endpoints into server.py

**Files:**
- Modify: `src/insightclass/web/server.py`
- Delete: `src/insightclass/web/experiment_viewer.py`
- Delete: `src/insightclass/web/demo.py`
- Modify: `src/insightclass/cli.py` (remove `view-experiments` and `demo` subcommands)

**Endpoints to merge into server.py:**

From `experiment_viewer.py`:
- `GET /api/experiments` — already exists in server.py, need to enrich with hyperparams/metrics/file flags
- `GET /api/experiments/{exp_id}/results.csv` — new
- `GET /api/experiments/{exp_id}/confusion_matrix` — new
- `GET /api/experiments/{exp_id}/results.png` — new

From `demo.py`:
- `POST /api/detect/image` — new (annotate with PIL, return base64)

**What to remove from server.py:**
- `GET /` Jinja2 template rendering (line ~80)
- `GET /dashboard` Jinja2 template rendering
- All `Jinja2Templates` usage
- Template dependency in imports

- [ ] **Step 1: Read current server.py, experiment_viewer.py, demo.py**
- [ ] **Step 2: Add experiment detail endpoints from experiment_viewer.py into server.py**
- [ ] **Step 3: Add `POST /api/detect/image` endpoint from demo.py into server.py**
- [ ] **Step 4: Remove Jinja2 template rendering routes (`GET /`, `GET /dashboard`)**
- [ ] **Step 5: Remove Jinja2 imports and Templates initialization**
- [ ] **Step 6: Add CORS middleware (`CORSMiddleware`) for dev server proxy**
- [ ] **Step 7: Add `GET /api/settings/display-names` endpoint (replaces Jinja2 injection of `display_names`)**
- [ ] **Step 8: Add `GET /api/settings/ui-defaults` endpoint (returns default model, confidence, IoU)**
- [ ] **Step 9: Delete `experiment_viewer.py` and `demo.py`**
- [ ] **Step 10: Update `cli.py` — remove `view-experiments` and `demo` subcommands, keep only `serve`**
- [ ] **Step 11: Verify all existing tests still pass: `python -m pytest tests/ -v`**
- [ ] **Step 12: Commit**

### Task 2: Add static file serving for SPA in production

**Files:**
- Modify: `src/insightclass/web/server.py`

- [ ] **Step 1: Add FastAPI `StaticFiles` mount for SPA build output**
  - Mount `/static` → `frontend/dist/static`
  - Add catch-all `GET /{path:path}` → serve `frontend/dist/index.html` (SPA fallback)
- [ ] **Step 2: Commit**

---

## Phase 2: React Frontend

### Task 3: Scaffold Vite + React + TypeScript project

**Files:**
- Create: `frontend/` (entire directory)
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Initialize Vite project**
  ```bash
  cd frontend && npm create vite@latest . -- --template react-ts
  ```
- [ ] **Step 2: Install dependencies**
  ```bash
  npm install react-router-dom chart.js react-chartjs-2
  npm install -D @types/react @types/react-dom
  ```
- [ ] **Step 3: Configure Vite proxy in `vite.config.ts`**
  ```ts
  export default defineConfig({
    plugins: [react()],
    server: {
      proxy: {
        '/api': 'http://localhost:8000',
      },
    },
  })
  ```
- [ ] **Step 4: Create project structure**
  ```
  frontend/src/
  ├── main.tsx
  ├── App.tsx
  ├── api/           # API service layer
  │   └── client.ts
  ├── pages/
  │   ├── Detection.tsx
  │   ├── Dashboard.tsx
  │   └── Experiments.tsx
  ├── components/    # Shared components
  └── styles/        # Global styles
  ```
- [ ] **Step 5: Set up React Router in App.tsx**
  - `/` → Detection page
  - `/dashboard` → Dashboard page
  - `/experiments` → Experiments page
- [ ] **Step 6: Create API client in `api/client.ts`**
  - Type-safe wrapper around `fetch` for all `/api/*` endpoints
  - Reuse types from `web/schemas.py` (manually define TS interfaces)
- [ ] **Step 7: Verify dev server starts: `npm run dev`**
- [ ] **Step 8: Commit**

### Task 4: Build Detection page (main page)

**Files:**
- Create: `frontend/src/pages/Detection.tsx`
- Create: `frontend/src/components/SourceSelector.tsx`
- Create: `frontend/src/components/Viewer.tsx`
- Create: `frontend/src/components/StatsBar.tsx`
- Create: `frontend/src/components/CameraSidebar.tsx`
- Create: `frontend/src/components/SettingsPanel.tsx`

**Sub-features to migrate from index.html:**
1. Source selector (RTSP / Webcam / Image / Video)
2. Video/canvas viewer with detection overlay
3. Detection loop (polling /api/detect/*)
4. Camera list sidebar (CRUD, connectivity test)
5. Model selector + confidence/IoU sliders
6. Settings modal (RTSP credentials, CSV import)
7. File panel (uploaded files management)
8. Batch video detection + playback

- [ ] **Step 1: Build Detection page layout (3-column shell)**
- [ ] **Step 2: Build SourceSelector component**
- [ ] **Step 3: Build Viewer component with canvas overlay for bounding boxes**
- [ ] **Step 4: Implement Image detection mode (upload → POST /api/detect/frame → render)**
- [ ] **Step 5: Implement Webcam detection mode (getUserMedia → capture → POST /api/detect/frame loop)**
- [ ] **Step 6: Implement RTSP mode (MJPEG stream from /api/stream/rtsp + POST /api/detect/rtsp polling)**
- [ ] **Step 7: Implement Video mode (file upload → POST /api/detect/upload → playback with overlay)**
- [ ] **Step 8: Build StatsBar component (per-class counts, latency, frame count)**
- [ ] **Step 9: Build CameraSidebar component (list, add, edit, delete, test connectivity)**
- [ ] **Step 10: Build SettingsPanel component (RTSP credentials, CSV import, default model)**
- [ ] **Step 11: Implement batch video detection (upload → start → poll → playback)**
- [ ] **Step 12: Commit**

### Task 5: Build Dashboard page

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`
- Create: `frontend/src/components/dashboard/SummaryRow.tsx`
- Create: `frontend/src/components/dashboard/ChartGrid.tsx`
- Create: `frontend/src/components/dashboard/CameraGrid.tsx`

**Sub-features to migrate from dashboard.html:**
1. Summary counters (4 behaviors + online cameras)
2. Charts (donut, bar, line, heatmap) — use Chart.js
3. Camera grid with per-camera stats
4. Auto-refresh (5s polling /api/dashboard/stats)
5. Group filter (front/rear/custom)
6. Report export (CSV download)

- [ ] **Step 1: Build Dashboard page layout**
- [ ] **Step 2: Build SummaryRow component**
- [ ] **Step 3: Build ChartGrid with Chart.js (donut, bar, line)**
- [ ] **Step 4: Build CameraGrid component**
- [ ] **Step 5: Implement auto-refresh polling**
- [ ] **Step 6: Implement group filter**
- [ ] **Step 7: Implement report export**
- [ ] **Step 8: Commit**

### Task 6: Build Experiments page

**Files:**
- Create: `frontend/src/pages/Experiments.tsx`

**Sub-features to migrate from experiments.html:**
1. Experiment list sidebar with multi-select
2. Info cards (mAP50-95, mAP50, Precision, Recall)
3. Hyperparameters grid
4. Training curves (loss + mAP charts via Chart.js)
5. Results plot images (/api/experiments/{id}/results.png)
6. Confusion matrix images (/api/experiments/{id}/confusion_matrix)

- [ ] **Step 1: Build Experiments page layout (sidebar + main)**
- [ ] **Step 2: Implement experiment list with multi-select**
- [ ] **Step 3: Build info cards and hyperparameters grid**
- [ ] **Step 4: Implement training curves with Chart.js (GET /api/experiments/{id}/results.csv)**
- [ ] **Step 5: Display results.png and confusion_matrix images**
- [ ] **Step 6: Commit**

### Task 7: Build frontend and integrate with FastAPI

**Files:**
- Modify: `src/insightclass/web/server.py`
- Create: `frontend/dist/` (build output)

- [ ] **Step 1: Build React app: `cd frontend && npm run build`**
- [ ] **Step 2: Verify FastAPI serves SPA correctly from `frontend/dist/`**
- [ ] **Step 3: Test full flow: start server → open browser → navigate all 3 pages**
- [ ] **Step 4: Commit**

---

## Phase 3: Packaging (Future — Separate Plan)

- PyInstaller sidecar for Python inference process
- Tauri 2 shell for native window
- NSIS installer / portable exe
- Auto-updater

---

## API Contract Summary

All endpoints consolidated under one FastAPI app. Base: `http://localhost:{port}/api`

### Settings
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings/display-names` | Class display names (Chinese) |
| GET | `/api/settings/ui-defaults` | Default model, confidence, IoU |
| GET | `/api/settings/default-model` | Default model path |
| POST | `/api/settings/default-model` | Save default model path |
| GET | `/api/settings/rtsp-credentials` | RTSP credentials |
| POST | `/api/settings/rtsp-credentials` | Save RTSP credentials |

### Detection
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/detect/frame` | Single frame detection (multipart) |
| POST | `/api/detect/image` | Image detection with annotation (returns base64) |
| POST | `/api/detect/upload` | Full video detection |
| POST | `/api/detect/rtsp` | RTSP single-frame detection |
| POST | `/api/detect/batch-upload` | Upload multiple videos |
| POST | `/api/detect/batch/{id}` | Start batch detection |
| GET | `/api/detect/batch/{id}` | Poll batch status |
| GET | `/api/detect/batch/{id}/item/{index}` | Batch item detail |
| GET | `/api/detect/batch/{id}/export` | Export batch results |

### Cameras
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/cameras` | List cameras |
| POST | `/api/cameras` | Add camera |
| PUT | `/api/cameras/{ip}` | Update camera |
| DELETE | `/api/cameras/{ip}` | Delete camera |
| POST | `/api/cameras/import` | CSV import |
| GET | `/api/cameras/{ip}/test` | Test single camera |
| POST | `/api/cameras/test` | Test multiple cameras |

### Streaming
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/rtsp` | MJPEG stream proxy |
| POST | `/api/stream/stop` | Stop stream |
| GET | `/api/stream/status` | Stream status |

### Dashboard
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard/stats` | Aggregated stats |
| GET | `/api/dashboard/report` | Download CSV report |
| GET | `/api/dashboard/history` | 24h trend data |

### Experiments
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/experiments` | List experiments (with metrics) |
| GET | `/api/experiments/{id}/results.csv` | Training CSV data |
| GET | `/api/experiments/{id}/confusion_matrix` | Confusion matrix image |
| GET | `/api/experiments/{id}/results.png` | Results plot image |
