import type {
  Camera,
  DisplayNames,
  UiDefaults,
  ExperimentSummary,
  DashboardStats,
  HistoryEntry,
  RtspCredentials,
  FrameDetectionResponse,
  ImageDetectionResponse,
  VideoDetectionResponse,
  BatchJob,
  BatchItemDetail,
} from '../types'

const BASE = '/api'

// ---------------------------------------------------------------------------
// Core request helper
// ---------------------------------------------------------------------------

class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, options)
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }))
    throw new ApiError(body.error || res.statusText, res.status)
  }
  return res.json()
}

// Helper: build a JSON POST/PUT body
function jsonBody(data: Record<string, unknown>): RequestInit {
  return {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }
}

// ---------------------------------------------------------------------------
// Camera management
// ---------------------------------------------------------------------------

export const getCameras = () =>
  request<Camera[]>('/cameras')

export const addCamera = (data: { ip: string; name: string; note?: string }) =>
  request<Camera>('/cameras', { method: 'POST', ...jsonBody(data) })

export const updateCamera = (ip: string, data: { name: string; note?: string }) =>
  request<Camera>(`/cameras/${encodeURIComponent(ip)}`, { method: 'PUT', ...jsonBody(data) })

export const deleteCamera = (ip: string) =>
  request<void>(`/cameras/${encodeURIComponent(ip)}`, { method: 'DELETE' })

export const testCamera = (ip: string) =>
  request<{ ip: string; status: string }>(`/cameras/${encodeURIComponent(ip)}/test`)

export const testCameras = (cameras: string[] = []) =>
  request<Record<string, string>>('/cameras/test', { method: 'POST', ...jsonBody({ cameras }) })

export const importCamerasCsv = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return request<{ ok: boolean; imported: number; skipped: number; errors: string[] }>('/cameras/import', {
    method: 'POST',
    body: fd,
  })
}

// ---------------------------------------------------------------------------
// Detection
// ---------------------------------------------------------------------------

/** Single-frame detection (webcam / RTSP frame) */
export const detectFrame = (fd: FormData) =>
  request<FrameDetectionResponse>('/detect/frame', { method: 'POST', body: fd })

/** Image detection — returns annotated base64 image */
export const detectImage = (fd: FormData) =>
  request<ImageDetectionResponse>('/detect/image', { method: 'POST', body: fd })

/** Video upload detection */
export const detectUpload = (fd: FormData) =>
  request<VideoDetectionResponse>('/detect/upload', { method: 'POST', body: fd })

/** RTSP stream single-frame detection */
export const detectRtsp = (fd: FormData) =>
  request<FrameDetectionResponse>('/detect/rtsp', { method: 'POST', body: fd })

// ---------------------------------------------------------------------------
// Batch detection
// ---------------------------------------------------------------------------

/** Upload multiple videos for batch processing */
export const batchUpload = (files: File[]) => {
  const fd = new FormData()
  for (const f of files) fd.append('videos', f)
  return request<{ batch_id: string; status: string; item_count: number }>('/detect/batch-upload', {
    method: 'POST',
    body: fd,
  })
}

/** Start batch detection for an uploaded batch */
export const batchDetect = (batchId: string, fd: FormData) =>
  request<{ ok: boolean }>(`/detect/batch/${batchId}`, { method: 'POST', body: fd })

/** Get batch job status / results */
export const getBatchStatus = (batchId: string) =>
  request<BatchJob>(`/detect/batch/${batchId}`)

/** Get a single item from a batch */
export const getBatchItem = (batchId: string, index: number) =>
  request<BatchItemDetail>(`/detect/batch/${batchId}/item/${index}`)

/** Export batch results as JSON or CSV (returns blob URL) */
export const downloadBatchExport = async (batchId: string, format: 'json' | 'csv' = 'json') => {
  const res = await fetch(`${BASE}/detect/batch/${batchId}/export?format=${format}`)
  if (!res.ok) throw new ApiError(res.statusText, res.status)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = format === 'csv' ? `batch_${batchId}.csv` : `batch_${batchId}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// Stream management
// ---------------------------------------------------------------------------

export const stopStream = () =>
  request<{ ok: boolean }>('/stream/stop', { method: 'POST' })

export const getStreamStatus = () =>
  request<{ active: boolean; rtsp_url?: string }>('/stream/status')

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export const getDisplayNames = () =>
  request<DisplayNames>('/settings/display-names')

export const getUiDefaults = () =>
  request<UiDefaults>('/settings/ui-defaults')

export const getDefaultModel = () =>
  request<{ model: string }>('/settings/default-model')

export const setDefaultModel = (model: string) =>
  request<{ ok: boolean }>('/settings/default-model', { method: 'POST', ...jsonBody({ model }) })

export const getRtspCredentials = () =>
  request<RtspCredentials>('/settings/rtsp-credentials')

export const setRtspCredentials = (data: RtspCredentials) =>
  request<{ ok: boolean }>('/settings/rtsp-credentials', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })

// ---------------------------------------------------------------------------
// Experiments
// ---------------------------------------------------------------------------

export const getExperiments = () =>
  request<ExperimentSummary[]>('/experiments')

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export const getDashboardStats = () =>
  request<DashboardStats>('/dashboard/stats')

export const getDashboardHistory = () =>
  request<{ history: Record<string, HistoryEntry[]>; simulated: boolean }>('/dashboard/history')

export const downloadDashboardReport = async () => {
  const res = await fetch(`${BASE}/dashboard/report`)
  if (!res.ok) throw new ApiError(res.statusText, res.status)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'dashboard_report.csv'
  a.click()
  URL.revokeObjectURL(url)
}
