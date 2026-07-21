export interface DetectionOut {
  xyxy: number[]
  confidence: number
  class_id: number
  class_name: string
  display_name: string
}

export interface ImageDetectionResponse {
  image: string // base64 data URL
  detections: DetectionOut[]
  latency_ms: number
}

export interface RtspCredentials {
  username: string
  password: string
  port: number
}

export interface FrameDetectionResponse {
  detections: DetectionOut[]
  latency_ms: number
  frame_width: number
  frame_height: number
  frame_image: string
}

export interface FrameOut {
  frame_index: number
  detections: DetectionOut[]
}

export interface VideoDetectionResponse {
  frames: FrameOut[]
  frame_count: number
  fps: number
  total_latency_sec: number
  video_width: number
  video_height: number
}

export interface ExperimentSummary {
  experiment_id: string
  weights_path: string
  class_names: string[]
  metrics: Record<string, number>
  hyperparameters?: Record<string, unknown>
  has_results_csv?: boolean
  has_confusion_matrix?: boolean
  has_results_png?: boolean
}

export interface Camera {
  ip: string
  name: string
  group: string
  group_label?: string
  note?: string
  rtsp_url?: string
}

export interface DisplayNames {
  [key: string]: string
}

export type SourceMode = 'rtsp' | 'webcam' | 'image' | 'video' | 'batch'

export interface UiDefaults {
  model: string
  confidence: number
  iou: number
}

export type BatchStatus = 'pending' | 'processing' | 'done' | 'error'

export interface BatchJob {
  batch_id: string
  status: BatchStatus
  total_latency_sec: number
  items: BatchItem[]
}

export interface BatchItem {
  filename: string
  status: BatchStatus
  frame_count: number
  fps: number
  video_width: number
  video_height: number
  latency_sec: number
  error: string
  detection_summary: Record<string, number>
}

export interface BatchItemDetail extends BatchItem {
  frames: FrameOut[]
}

export interface HistoryEntry {
  time: string
  phone_use: number
  talking: number
  sleeping: number
  standing: number
}

export interface DashboardStats {
  cameras: DashboardCamera[]
  total: Record<string, number>
  online_count: number
  total_cameras: number
}

export interface DashboardCamera {
  ip: string
  name: string
  group: string
  group_label: string
  online: boolean
  stats: Record<string, number>
  last_update: string | null
}
