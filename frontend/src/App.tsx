import { useState, useRef, useCallback, useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import type { Camera, DetectionOut, DisplayNames, SourceMode, BatchItem, LlmSettings, SystemStatus } from './types'
import { addCamera, updateCamera, deleteCamera, detectFrame, detectRtsp, detectImage, detectUpload, getDisplayNames, getStreamStatus, stopStream, getExperiments, getUiDefaults, getCameras, getSystemStatus, testCameras, batchUpload, batchDetect as batchDetectApi, getBatchStatus, getBatchItem, downloadBatchExport, importCamerasCsv, getRtspCredentials, setRtspCredentials as saveRtspCredentialsApi, setDefaultModel, getLlmSettings, setLlmSettings, testLlmConnection } from './api/client'

// Health check constants
const HEALTH_CHECK_INTERVAL = 10000 // 10s
const MAX_RECONNECT_ATTEMPTS = 5
const DETECT_INTERVAL = 1000 // 1s
type CameraConnectionStatus = 'unknown' | 'testing' | 'connected' | 'disconnected'

function App() {
  // Camera state
  const [cameras, setCameras] = useState<Camera[]>([])
  const [selectedCamera, setSelectedCamera] = useState<Camera | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingCamera, setEditingCamera] = useState<Camera | null>(null)
  const [testingCameras, setTestingCameras] = useState(false)
  const [cameraStatuses, setCameraStatuses] = useState<Record<string, CameraConnectionStatus>>({})

  // Camera & stream state
  const [rtspStreamUrl, setRtspStreamUrl] = useState<string | null>(null)

  // Detection state
  const [source, setSource] = useState<SourceMode>('rtsp')
  const [running, setRunning] = useState(false)
  const [loading, setLoading] = useState(false)
  const [detections, setDetections] = useState<DetectionOut[]>([])
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [frameCount, setFrameCount] = useState(0)
  const [annotatedImage, setAnnotatedImage] = useState<string | null>(null)
  const [displayNames, setDisplayNames] = useState<DisplayNames>({})
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null)
  const [sourceError, setSourceError] = useState('')
  const [viewerRevision, setViewerRevision] = useState(0)

  // Model controls
  const [model, setModel] = useState('')
  const [confidence, setConfidence] = useState(0.5)
  const [iou, setIou] = useState(0.45)
  const [models, setModels] = useState<string[]>([])

  // Video detection result
  const [videoFileUrl, setVideoFileUrl] = useState<string | null>(null)

  // File list state
  const [fileList, setFileList] = useState<Array<{
    id: number
    file: File
    type: 'image' | 'video'
    name: string
    size: number
    thumbnailUrl: string
    status: 'pending' | 'detecting' | 'done' | 'error'
    selected: boolean
  }>>([])
  const [activeFileId, setActiveFileId] = useState<number | null>(null)
  const [filePanelOpen, setFilePanelOpen] = useState(false)
  const [filePanelTab, setFilePanelTab] = useState<'image' | 'video'>('image')
  const [selectionMode, setSelectionMode] = useState(false)
  const fileIdCounter = useRef(0)

  // Batch detection state
  const [batchFiles, setBatchFiles] = useState<File[]>([])
  const [batchId, setBatchId] = useState<string | null>(null)
  const [batchItems, setBatchItems] = useState<BatchItem[]>([])
  const [batchProcessing, setBatchProcessing] = useState(false)

  // Playback modal state
  const [playbackModalOpen, setPlaybackModalOpen] = useState(false)
  const [playbackItem, setPlaybackItem] = useState<any>(null)
  const [playbackResults, setPlaybackResults] = useState<any>(null)

  // Settings modal state
  const [settingsModalOpen, setSettingsModalOpen] = useState(false)
  const [rtspCredentials, setRtspCredentials] = useState({ username: 'admin', password: '', port: 554 })
  const [llmSettings, setLlmSettingsState] = useState<LlmSettings | null>(null)
  const [llmForm, setLlmForm] = useState({ base_url: '', model: '', api_key: '', timeout: 60 })
  const [llmSaving, setLlmSaving] = useState(false)
  const [llmTesting, setLlmTesting] = useState(false)
  const [llmTestMessage, setLlmTestMessage] = useState('')

  // Health check state
  const [, setStreamHealthy] = useState<boolean | null>(null)
  const [, setReconnectAttempts] = useState(0)

  // Refs
  const detectTimerRef = useRef<number | null>(null)
  const healthTimerRef = useRef<number | null>(null)
  const detectionInFlightRef = useRef(false)
  const detectionGenerationRef = useRef(0)
  const webcamStreamRef = useRef<MediaStream | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  // Load cameras
  const loadCameras = useCallback(async () => {
    try {
      const data = await getCameras()
      setCameras(data)
    } catch (err) {
      console.error('Failed to load cameras:', err)
    }
  }, [])

  // Load display names, models, and ui defaults
  useEffect(() => {
    loadCameras()
    getDisplayNames().then(setDisplayNames).catch(() => {})
    getExperiments().then((exps) => {
      const names = exps.map((e) => e.experiment_id)
      setModels(names)
      if (names.length > 0 && !model) setModel(names[0])
    }).catch(() => {})
    getUiDefaults().then((d) => {
      if (!confidence || confidence === 0.5) setConfidence(d.confidence)
      if (!iou || iou === 0.45) setIou(d.iou)
      if (!model && d.model) setModel(d.model)
    }).catch(() => {})
    getRtspCredentials().then(setRtspCredentials).catch(() => {})
  }, [])

  useEffect(() => {
    let active = true
    const pollStatus = async () => {
      try {
        const status = await getSystemStatus()
        if (active) setSystemStatus(status)
      } catch {
        // The app remains usable while a transient status poll fails.
      }
    }
    void pollStatus()
    const timer = window.setInterval(pollStatus, 2000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    if (!settingsModalOpen) return
    getLlmSettings().then((settings) => {
      setLlmSettingsState(settings)
      setLlmForm({
        base_url: settings.base_url,
        model: settings.model,
        api_key: '',
        timeout: settings.timeout,
      })
    }).catch(() => setLlmSettingsState(null))
  }, [settingsModalOpen])

  // ---- Camera management ----
  const handleSelectCamera = (camera: Camera) => {
    setSelectedCamera(camera)
  }

  const handleDeleteCamera = async (camera: Camera) => {
    if (!confirm(`确定要删除摄像头 "${camera.name}" (${camera.ip}) 吗？`)) return
    try {
      await deleteCamera(camera.ip)
      setCameras((prev) => prev.filter((c) => c.ip !== camera.ip))
      if (selectedCamera?.ip === camera.ip) setSelectedCamera(null)
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除失败')
    }
  }

  const handleTestCameras = useCallback(async () => {
    if (testingCameras) return
    setTestingCameras(true)
    const ips = cameras.map((camera) => camera.ip)
    setCameraStatuses((prev) => ({
      ...prev,
      ...Object.fromEntries(ips.map((ip) => [ip, 'testing' as const])),
    }))

    try {
      const results = await testCameras(ips)
      setCameraStatuses((prev) => ({
        ...prev,
        ...Object.fromEntries(ips.map((ip) => [
          ip,
          results[ip] === 'connected' ? 'connected' as const : 'disconnected' as const,
        ])),
      }))
    } catch {
      setCameraStatuses((prev) => ({
        ...prev,
        ...Object.fromEntries(ips.map((ip) => [ip, 'disconnected' as const])),
      }))
    } finally {
      setTestingCameras(false)
    }
  }, [cameras, testingCameras])

  const stopWebcam = useCallback(() => {
    webcamStreamRef.current?.getTracks().forEach((track) => track.stop())
    webcamStreamRef.current = null
    const video = videoRef.current
    if (video?.srcObject) {
      video.pause()
      video.srcObject = null
    }
  }, [])

  // ---- Stop all detection ----
  const stopAll = useCallback(() => {
    detectionGenerationRef.current += 1
    if (detectTimerRef.current !== null) {
      clearInterval(detectTimerRef.current)
      detectTimerRef.current = null
    }
    if (healthTimerRef.current !== null) {
      clearInterval(healthTimerRef.current)
      healthTimerRef.current = null
    }
    setRunning(false)
    setDetections([])
    setLatencyMs(null)
    setFrameCount(0)
    setStreamHealthy(null)
    setReconnectAttempts(0)
    setSourceError('')
    stopWebcam()
  }, [stopWebcam])

  // ---- Reset stats ----
  const resetStats = useCallback(() => {
    setDetections([])
    setLatencyMs(null)
    setFrameCount(0)
    setAnnotatedImage(null)
    setVideoFileUrl(null)
    setBatchItems([])
  }, [])

  // ---- File management ----
  const addFilesToList = useCallback((files: FileList | File[]) => {
    const newEntries = Array.from(files).map(file => {
      const type: 'image' | 'video' = file.type.startsWith('video/') ? 'video' : 'image'
      const id = ++fileIdCounter.current
      return {
        id,
        file,
        type,
        name: file.name,
        size: file.size,
        thumbnailUrl: URL.createObjectURL(file),
        status: 'pending' as const,
        selected: false
      }
    })

    setFileList(prev => [...prev, ...newEntries])
    setFilePanelOpen(true)

    if (newEntries.length > 0) {
      setActiveFileId(newEntries[0].id)
    }
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.currentTarget.classList.add('dragover')
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.currentTarget.classList.remove('dragover')
  }, [])

  const handleDrop = useCallback((e: React.DragEvent, _type: 'image' | 'video') => {
    e.preventDefault()
    e.currentTarget.classList.remove('dragover')
    if (e.dataTransfer.files.length > 0) {
      addFilesToList(e.dataTransfer.files)
    }
  }, [addFilesToList])

  const removeFile = useCallback((id: number) => {
    setFileList(prev => {
      const entry = prev.find(f => f.id === id)
      if (entry?.thumbnailUrl) URL.revokeObjectURL(entry.thumbnailUrl)
      return prev.filter(f => f.id !== id)
    })
    if (activeFileId === id) setActiveFileId(null)
  }, [activeFileId])

  const clearAllFiles = useCallback(() => {
    fileList.forEach(f => {
      if (f.thumbnailUrl) URL.revokeObjectURL(f.thumbnailUrl)
    })
    setFileList([])
    setActiveFileId(null)
  }, [fileList])

  const handleDetectFile = useCallback(async (fileId: number) => {
    const entry = fileList.find(f => f.id === fileId)
    if (!entry || entry.status === 'detecting') return

    setFileList(prev => prev.map(f => f.id === fileId ? { ...f, status: 'detecting' as const } : f))
    setLoading(true)
    resetStats()
    setActiveFileId(fileId)

    try {
      const fd = new FormData()
      fd.append('file', entry.file)
      fd.append('confidence', String(confidence))
      fd.append('iou', String(iou))
      if (model) fd.append('model', model)

      if (entry.type === 'image') {
        const res = await detectImage(fd)
        setAnnotatedImage(res.image)
        setDetections(res.detections)
        setLatencyMs(res.latency_ms)
        setFrameCount(1)
        setSource('image')
      } else {
        const res = await detectUpload(fd)
        setDetections(res.frames.flatMap(f => f.detections))
        setLatencyMs(res.total_latency_sec * 1000)
        setFrameCount(res.frame_count)
        setVideoFileUrl(URL.createObjectURL(entry.file))
        setSource('video')
      }

      setFileList(prev => prev.map(f => f.id === fileId ? { ...f, status: 'done' as const } : f))
    } catch (err) {
      console.error('Detection failed:', err)
      setFileList(prev => prev.map(f => f.id === fileId ? { ...f, status: 'error' as const } : f))
    } finally {
      setLoading(false)
    }
  }, [fileList, confidence, iou, model, resetStats])

  // ---- Batch detection ----
  const batchPollAbortRef = useRef(false)

  const batchPollProgress = useCallback(async (id: string) => {
    const MAX_RETRIES = 3
    let retries = 0

    while (!batchPollAbortRef.current) {
      await new Promise(r => setTimeout(r, 1000))
      try {
        const data = await getBatchStatus(id)
        retries = 0
        setBatchItems(data.items)

        if (data.status === 'done' || data.status === 'error') break
      } catch {
        retries++
        if (retries >= MAX_RETRIES) break
      }
    }
  }, [])

  const batchDetect = useCallback(async () => {
    if (batchFiles.length === 0 || batchProcessing) return
    setBatchProcessing(true)
    batchPollAbortRef.current = false

    try {
      const uploadRes = await batchUpload(batchFiles)
      setBatchId(uploadRes.batch_id)

      const fd = new FormData()
      fd.append('model', model)
      fd.append('confidence', String(confidence))
      fd.append('iou', String(iou))
      await batchDetectApi(uploadRes.batch_id, fd)

      await batchPollProgress(uploadRes.batch_id)
    } catch (err) {
      console.error('Batch detection failed:', err)
      alert('批量检测失败: ' + (err instanceof Error ? err.message : '未知错误'))
    }

    setBatchProcessing(false)
  }, [batchFiles, batchProcessing, model, confidence, iou, batchPollProgress])

  const batchExport = useCallback(async (format: 'csv' | 'json') => {
    if (!batchId) return
    await downloadBatchExport(batchId, format)
  }, [batchId])

  // ---- Playback modal ----
  const openPlaybackModal = useCallback(async (index: number) => {
    if (!batchId) return
    const data = await getBatchItem(batchId, index)
    setPlaybackItem(batchItems[index])
    setPlaybackResults(data)
    setPlaybackModalOpen(true)
  }, [batchId, batchItems])

  const closePlaybackModal = useCallback(() => {
    setPlaybackModalOpen(false)
    setPlaybackItem(null)
    setPlaybackResults(null)
  }, [])

  // ---- Settings modal ----
  const handleImportCsv = useCallback(async (file: File) => {
    try {
      const result = await importCamerasCsv(file)
      alert(`导入完成: ${result.imported} 个摄像头`)
      loadCameras()
    } catch (err) {
      alert(`导入失败: ${err instanceof Error ? err.message : '未知错误'}`)
    }
  }, [loadCameras])

  const handleSaveRtspCredentials = useCallback(async () => {
    try {
      await saveRtspCredentialsApi(rtspCredentials)
      setSettingsModalOpen(false)
    } catch (err) {
      alert(`保存失败: ${err instanceof Error ? err.message : '未知错误'}`)
    }
  }, [rtspCredentials])

  const handleSaveLlm = useCallback(async () => {
    setLlmSaving(true)
    setLlmTestMessage('')
    try {
      const settings = await setLlmSettings(llmForm)
      setLlmSettingsState(settings)
      setLlmForm((prev) => ({ ...prev, api_key: '' }))
      setLlmTestMessage('大模型设置已保存')
    } catch (err) {
      setLlmTestMessage(err instanceof Error ? err.message : '保存失败')
    } finally {
      setLlmSaving(false)
    }
  }, [llmForm])

  const handleTestLlm = useCallback(async () => {
    setLlmTesting(true)
    setLlmTestMessage('正在测试连接...')
    try {
      const result = await testLlmConnection()
      setLlmTestMessage(`连接成功: ${result.preview}`)
    } catch (err) {
      setLlmTestMessage(err instanceof Error ? err.message : '连接失败')
    } finally {
      setLlmTesting(false)
    }
  }, [])

  const handleSetDefaultModel = useCallback(async () => {
    if (!model) return
    await setDefaultModel(model)
    const btn = document.getElementById('btn-set-default')
    btn?.classList.add('saved')
    setTimeout(() => btn?.classList.remove('saved'), 1500)
  }, [model])

  // ---- Stream health check ----
  const startHealthCheck = useCallback((cameraIp: string) => {
    if (healthTimerRef.current !== null) {
      clearInterval(healthTimerRef.current)
    }

    const check = async () => {
      try {
        const status = await getStreamStatus(cameraIp)
        const isOk = status.active === true
        setStreamHealthy(isOk)
        setCameraStatuses((prev) => ({
          ...prev,
          [cameraIp]: isOk ? 'connected' : status.status === 'connecting' ? 'testing' : 'disconnected',
        }))

        if (status.status === 'error' || status.status === 'idle') {
          setReconnectAttempts((prev) => {
            if (prev >= MAX_RECONNECT_ATTEMPTS) {
              setStreamHealthy(false)
              return prev
            }
            setRtspStreamUrl(`/api/stream/rtsp?camera_ip=${encodeURIComponent(cameraIp)}&_t=${Date.now()}`)
            return prev + 1
          })
        } else if (isOk) {
          setReconnectAttempts(0)
        }
      } catch {
        setStreamHealthy(false)
        setCameraStatuses((prev) => ({ ...prev, [cameraIp]: 'disconnected' }))
      }
    }

    void check()
    healthTimerRef.current = window.setInterval(check, HEALTH_CHECK_INTERVAL)
  }, [])

  // ---- Switch source ----
  const handleSourceChange = useCallback((newSource: SourceMode) => {
    batchPollAbortRef.current = true
    stopAll()
    resetStats()
    setSource(newSource)
    if (newSource !== 'rtsp') {
      setRtspStreamUrl(null)
      if (selectedCamera) void stopStream(selectedCamera.ip).catch(() => {})
    }
  }, [selectedCamera, stopAll, resetStats])

  // ---- React to camera selection ----
  useEffect(() => {
    if (!selectedCamera) {
      setRtspStreamUrl(null)
      return
    }

    stopAll()
    resetStats()
    setSource('rtsp')

    const streamUrl = `/api/stream/rtsp?camera_ip=${encodeURIComponent(selectedCamera.ip)}`
    setRtspStreamUrl(streamUrl)

    startHealthCheck(selectedCamera.ip)
  }, [selectedCamera, resetStats, startHealthCheck, stopAll])

  // ---- Start detection ----
  const handleStart = useCallback(async () => {
    if (source === 'rtsp') {
      if (!selectedCamera) return
      stopAll()
      resetStats()
      setRunning(true)
      const generation = detectionGenerationRef.current

      const doDetect = async () => {
        if (detectionInFlightRef.current || detectionGenerationRef.current !== generation) return
        detectionInFlightRef.current = true
        const fd = new FormData()
        fd.append('camera_ip', selectedCamera.ip)
        try {
          const res = await detectRtsp(fd)
          if (detectionGenerationRef.current === generation && res.frame_width > 0 && res.frame_height > 0) {
            setDetections(res.detections)
            setLatencyMs(res.latency_ms)
            setFrameCount((c) => c + 1)
            setSourceError('')
          }
        } catch (err) {
          if (detectionGenerationRef.current === generation) {
            setSourceError(err instanceof Error ? err.message : '摄像头检测失败')
          }
        } finally {
          detectionInFlightRef.current = false
        }
      }

      void doDetect()
      detectTimerRef.current = window.setInterval(doDetect, DETECT_INTERVAL)
      startHealthCheck(selectedCamera.ip)
    } else if (source === 'webcam') {
      stopAll()
      resetStats()
      setLoading(true)
      const generation = detectionGenerationRef.current
      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error('当前 WebView 不支持摄像头访问')
        }
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        if (detectionGenerationRef.current !== generation) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        const video = videoRef.current
        if (!video) throw new Error('摄像头预览未就绪')
        webcamStreamRef.current = stream
        video.srcObject = stream
        await video.play()
        setRunning(true)

        const capture = document.createElement('canvas')
        const doDetect = async () => {
          if (detectionInFlightRef.current || detectionGenerationRef.current !== generation) return
          if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !video.videoWidth || !video.videoHeight) return
          detectionInFlightRef.current = true
          try {
            capture.width = video.videoWidth
            capture.height = video.videoHeight
            capture.getContext('2d')?.drawImage(video, 0, 0)
            const blob = await new Promise<Blob | null>((resolve) => capture.toBlob(resolve, 'image/jpeg', 0.85))
            if (!blob) throw new Error('无法读取摄像头画面')
            const fd = new FormData()
            fd.append('image', blob, 'webcam.jpg')
            fd.append('confidence', String(confidence))
            fd.append('iou', String(iou))
            if (model) fd.append('model', model)
            const res = await detectFrame(fd)
            if (detectionGenerationRef.current === generation) {
              setDetections(res.detections)
              setLatencyMs(res.latency_ms)
              setFrameCount((count) => count + 1)
              setSourceError('')
            }
          } catch (err) {
            if (detectionGenerationRef.current === generation) {
              setSourceError(err instanceof Error ? err.message : '电脑摄像头检测失败')
            }
          } finally {
            detectionInFlightRef.current = false
          }
        }
        void doDetect()
        detectTimerRef.current = window.setInterval(doDetect, DETECT_INTERVAL)
      } catch (err) {
        stopWebcam()
        setRunning(false)
        setSourceError(err instanceof Error ? err.message : '无法连接电脑摄像头')
      } finally {
        setLoading(false)
      }
    } else if (source === 'image') {
      document.querySelector<HTMLInputElement>('#image-input')?.click()
    } else if (source === 'video') {
      document.querySelector<HTMLInputElement>('#video-input')?.click()
    } else if (source === 'batch') {
      batchDetect()
    }
  }, [source, selectedCamera, stopAll, resetStats, startHealthCheck, batchDetect, confidence, iou, model, stopWebcam])

  // ---- Stop detection ----
  const handleStop = useCallback(() => {
    stopAll()
    if (source === 'rtsp' && selectedCamera) {
      void stopStream(selectedCamera.ip).catch(() => {})
    }
  }, [source, selectedCamera, stopAll])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      batchPollAbortRef.current = true
      detectionGenerationRef.current += 1
      if (detectTimerRef.current !== null) clearInterval(detectTimerRef.current)
      if (healthTimerRef.current !== null) clearInterval(healthTimerRef.current)
      stopWebcam()
    }
  }, [stopWebcam])

  useEffect(() => {
    const canvas = canvasRef.current
    const parent = canvas?.parentElement
    if (!parent) return
    const observer = new ResizeObserver(() => setViewerRevision((revision) => revision + 1))
    observer.observe(parent)
    return () => observer.disconnect()
  }, [])

  // Draw detections on canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Resize canvas to match parent
    const parent = canvas.parentElement
    if (parent) {
      canvas.width = parent.clientWidth
      canvas.height = parent.clientHeight
    }

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    if (detections.length === 0) return

    // Calculate scale
    const img = imageRef.current
    const video = videoRef.current
    const sourceWidth = img?.naturalWidth || video?.videoWidth || 0
    const sourceHeight = img?.naturalHeight || video?.videoHeight || 0
    if (!sourceWidth || !sourceHeight) return
    const scale = Math.min(canvas.width / sourceWidth, canvas.height / sourceHeight)
    const offsetX = (canvas.width - sourceWidth * scale) / 2
    const offsetY = (canvas.height - sourceHeight * scale) / 2

    // Draw detections
    const COLORS: Record<string, string> = {
      phone_use: '#ef4444',
      talking: '#3b82f6',
      sleeping: '#eab308',
      standing: '#22c55e',
    }

    const LINE_W = 2
    const FONT_SIZE = 12
    const FONT = `600 ${FONT_SIZE}px 'Noto Sans SC', sans-serif`
    const PAD = 4
    const LABEL_H = FONT_SIZE + PAD * 2

    for (const d of detections) {
      const [x1, y1, x2, y2] = d.xyxy
      const rx1 = offsetX + x1 * scale
      const ry1 = offsetY + y1 * scale
      const rx2 = offsetX + x2 * scale
      const ry2 = offsetY + y2 * scale
      const w = rx2 - rx1
      const h = ry2 - ry1
      const color = COLORS[d.class_name] || '#888'

      ctx.strokeStyle = color
      ctx.lineWidth = LINE_W
      ctx.strokeRect(rx1, ry1, w, h)

      const displayName = displayNames[d.class_name] || d.class_name
      const label = `${displayName} ${(d.confidence * 100).toFixed(0)}%`
      ctx.font = FONT
      const tm = ctx.measureText(label)
      ctx.fillStyle = color
      ctx.beginPath()
      const labelTop = Math.max(offsetY, ry1 - LABEL_H)
      ctx.roundRect(rx1, labelTop, tm.width + PAD * 2, LABEL_H, 3)
      ctx.fill()
      ctx.fillStyle = '#fff'
      ctx.fillText(label, rx1 + PAD, labelTop + FONT_SIZE + PAD)
    }
  }, [detections, displayNames, viewerRevision])

  // Playback video detection overlay sync
  useEffect(() => {
    if (!playbackModalOpen || !playbackResults) return
    const video = document.getElementById('playback-video') as HTMLVideoElement
    const canvas = document.getElementById('playback-canvas') as HTMLCanvasElement
    if (!video || !canvas) return

    const file = batchFiles.find(f => f.name === playbackItem?.filename)
    if (file) {
      const url = URL.createObjectURL(file)
      video.src = url
      video.load()
      return () => URL.revokeObjectURL(url)
    }
  }, [playbackModalOpen, playbackResults, playbackItem, batchFiles])

  useEffect(() => {
    if (!playbackModalOpen || !playbackResults) return
    const video = document.getElementById('playback-video') as HTMLVideoElement
    const canvas = document.getElementById('playback-canvas') as HTMLCanvasElement
    if (!video || !canvas) return

    const COLORS: Record<string, string> = {
      phone_use: '#ef4444',
      talking: '#3b82f6',
      sleeping: '#eab308',
      standing: '#22c55e',
    }

    let animId: number
    const render = () => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      canvas.width = canvas.clientWidth
      canvas.height = canvas.clientHeight
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      const frames = playbackResults.frames
      const fps = playbackResults.fps || 25
      if (frames && frames.length > 0) {
        const curFrame = Math.floor(video.currentTime * fps)
        const det = frames.find((f: any) => f.frame_index === curFrame)
        if (det) {
          const vw = video.videoWidth || 640
          const vh = video.videoHeight || 480
          const sx = canvas.width / vw
          const sy = canvas.height / vh
          for (const d of det.detections) {
            const [x1, y1, x2, y2] = d.xyxy
            const rx1 = x1 * sx, ry1 = y1 * sy
            const rx2 = x2 * sx, ry2 = y2 * sy
            const color = COLORS[d.class_name] || '#888'
            ctx.strokeStyle = color
            ctx.lineWidth = 2
            ctx.strokeRect(rx1, ry1, rx2 - rx1, ry2 - ry1)
            const label = `${d.display_name || d.class_name} ${(d.confidence * 100).toFixed(0)}%`
            ctx.font = "600 12px 'Noto Sans SC', sans-serif"
            const tm = ctx.measureText(label)
            const lh = 20
            ctx.fillStyle = color
            ctx.beginPath()
            ctx.roundRect(rx1, ry1 - lh - 4, tm.width + 8, lh + 4, 3)
            ctx.fill()
            ctx.fillStyle = '#fff'
            ctx.fillText(label, rx1 + 4, ry1 - 5)
          }
        }
      }
      if (!video.paused) animId = requestAnimationFrame(render)
    }

    video.addEventListener('play', render)
    video.addEventListener('seeked', render)
    if (!video.paused) render()
    return () => {
      cancelAnimationFrame(animId)
      video.removeEventListener('play', render)
      video.removeEventListener('seeked', render)
    }
  }, [playbackModalOpen, playbackResults])

  // Group cameras
  const groupedCameras = cameras.reduce<Record<string, Camera[]>>((acc, camera) => {
    const group = camera.group || 'custom'
    if (!acc[group]) acc[group] = []
    acc[group].push(camera)
    return acc
  }, {})

  const getGroupLabel = (group: string): string => {
    const labels: Record<string, string> = {
      front: '前排摄像头',
      rear: '后排摄像头',
      custom: '自定义分组',
    }
    return labels[group] || group
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="*" element={<>
      <div className="app">
        {/* Left sidebar */}
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-icon">
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                <rect width="32" height="32" rx="8" fill="url(#brand-grad)" />
                <path d="M8 16C8 11.58 11.58 8 16 8s8 3.58 8 8-3.58 8-8 8" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
                <circle cx="16" cy="16" r="3" fill="#fff" />
                <path d="M16 10v-2M16 24v-2M10 16H8M24 16h-2" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" opacity=".6" />
                <defs>
                  <linearGradient id="brand-grad" x1="0" y1="0" x2="32" y2="32">
                    <stop stopColor="#6366f1" />
                    <stop offset="1" stopColor="#06b6d4" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <div className="brand-text">
              <span className="brand-name">InsightClass</span>
              <span className="brand-sub">深见课堂</span>
            </div>
          </div>

          {/* Top Controls */}
          <div className="sidebar-controls">
            <div className="sidebar-section">
              <div className="section-label">检测源</div>
              <nav className="source-nav">
                <button className={`source-btn ${source === 'rtsp' ? 'active' : ''}`} onClick={() => handleSourceChange('rtsp')}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
                  <span>RTSP 监控</span>
                  <em>实时</em>
                </button>
                <button className={`source-btn ${source === 'webcam' ? 'active' : ''}`} onClick={() => handleSourceChange('webcam')}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>
                  <span>电脑摄像头</span>
                </button>
                <button className={`source-btn ${source === 'image' ? 'active' : ''}`} onClick={() => handleSourceChange('image')}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
                  <span>图片检测</span>
                </button>
                <button className={`source-btn ${source === 'video' ? 'active' : ''}`} onClick={() => handleSourceChange('video')}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                  <span>视频检测</span>
                </button>
                <button className={`source-btn ${source === 'batch' ? 'active' : ''}`} onClick={() => handleSourceChange('batch')}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3v4M8 3v4"/></svg>
                  <span>批量检测</span>
                </button>
              </nav>
            </div>

            {/* Webcam Panel */}
            <div className={`sidebar-section source-panel ${source === 'webcam' ? 'active' : ''}`}>
              <div className="section-label">电脑摄像头</div>
              <p className="panel-hint">点击右侧「开始检测」启动笔记本摄像头</p>
            </div>

            {/* Image Panel */}
            <div className={`sidebar-section source-panel ${source === 'image' ? 'active' : ''}`}>
              <div className="section-label">图片上传</div>
              <label className="upload-zone" id="image-drop"
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, 'image')}
              >
                <input id="image-input" type="file" accept="image/*" multiple onChange={(e) => {
                  if (e.target.files) addFilesToList(e.target.files)
                  e.target.value = ''
                }} />
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                <span>拖拽或点击选择图片</span>
                <em>支持 JPG / PNG</em>
              </label>
            </div>

            {/* Video Panel */}
            <div className={`sidebar-section source-panel ${source === 'video' ? 'active' : ''}`}>
              <div className="section-label">视频上传</div>
              <label className="upload-zone upload-zone-sm" id="video-drop"
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, 'video')}
              >
                <input id="video-input" type="file" accept="video/*" multiple onChange={(e) => {
                  if (e.target.files) addFilesToList(e.target.files)
                  e.target.value = ''
                }} />
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                <span>拖拽或点击上传视频</span>
                <em>MP4 / AVI / MOV · 选择后即时预览</em>
              </label>
            </div>

            {/* Batch Panel */}
            <div className={`sidebar-section source-panel ${source === 'batch' ? 'active' : ''}`}>
              <div className="section-label">批量视频检测</div>
              <label className="upload-zone upload-zone-sm" id="batch-drop">
                <input type="file" accept="video/*" multiple onChange={(e) => {
                  if (e.target.files) {
                    setBatchFiles(prev => [...prev, ...Array.from(e.target.files!)])
                  }
                  e.target.value = ''
                }} />
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                <span>选择多个视频文件</span>
                <em>支持同时上传多个视频进行批量检测</em>
              </label>

              <div className={`batch-queue ${batchFiles.length === 0 ? 'hidden' : ''}`}>
                <div className="batch-queue-header">
                  <span>文件队列</span>
                  <span className="batch-queue-count">{batchFiles.length}</span>
                </div>
                <div className="batch-queue-list">
                  {batchFiles.map((file, i) => (
                    <div key={`${file.name}-${i}`} className="batch-item">
                      <span className="batch-item-name" title={file.name}>{file.name}</span>
                      <button className="batch-item-remove" onClick={() => setBatchFiles(prev => prev.filter((_, idx) => idx !== i))}>&times;</button>
                    </div>
                  ))}
                </div>
                <div className="batch-actions">
                  <button className="btn-detect" onClick={batchDetect} disabled={batchProcessing || batchFiles.length === 0}>
                    {batchProcessing ? '处理中...' : '开始批量检测'}
                  </button>
                  <button className="btn-clear" onClick={() => { setBatchFiles([]); setBatchItems([]); setBatchId(null) }}>清空队列</button>
                </div>
              </div>

              <div className={`batch-total-progress ${batchItems.length === 0 ? 'hidden' : ''}`}>
                <div className="batch-total-bar">
                  <div className="batch-total-bar-fill" style={{ width: `${batchItems.length > 0 ? (batchItems.filter(i => i.status === 'done').length / batchItems.length * 100) : 0}%` }} />
                </div>
                <div className="batch-total-text">
                  {batchItems.filter(i => i.status === 'done').length} / {batchItems.length} 完成
                </div>
              </div>

              <div className={`batch-export-row ${batchId && batchItems.length > 0 && batchItems.every(i => i.status === 'done') ? '' : 'hidden'}`}>
                <button className="btn-export" onClick={() => batchExport('csv')}>导出 CSV</button>
                <button className="btn-export" onClick={() => batchExport('json')}>导出 JSON</button>
              </div>
            </div>
          </div>

          {/* Model & Params (bottom) */}
          <div className="sidebar-section params-section">
            <div className="section-label">模型与参数</div>
            <div className="param-row">
              <label>
                模型
                <button
                  className="btn-set-default"
                  id="btn-set-default"
                  title="设为默认模型"
                  onClick={handleSetDefaultModel}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                  </svg>
                </button>
              </label>
              <select value={model} onChange={(e) => setModel(e.target.value)}>
                {models.length === 0 && <option value="">无可用模型</option>}
                {models.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
            <div className="param-row">
              <label>置信度 <em>{confidence.toFixed(2)}</em></label>
              <input type="range" min="0.05" max="0.95" step="0.05" value={confidence} onChange={(e) => setConfidence(parseFloat(e.target.value))} />
            </div>
            <div className="param-row">
              <label>IoU <em>{iou.toFixed(2)}</em></label>
              <input type="range" min="0.1" max="0.9" step="0.05" value={iou} onChange={(e) => setIou(parseFloat(e.target.value))} />
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <main className="main">
          {/* Header */}
          <header className="header">
            <div className="header-left">
              <h1>{source === 'batch' ? '批量检测' : '实时检测'}</h1>
              <span className="header-badge" id="source-label">
                {source === 'rtsp' ? 'RTSP 监控' : source === 'webcam' ? '电脑摄像头' : source === 'image' ? '图片检测' : source === 'video' ? '视频检测' : '批量检测'}
              </span>
            </div>
            <div className="header-actions">
              <button className="btn-ctrl" id="btn-settings" title="设置" onClick={() => setSettingsModalOpen(true)}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.32 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
                设置
              </button>
              <button className="btn-ctrl" id="btn-dashboard" title="打开监控大屏" onClick={() => window.open('/dashboard', '_blank')}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
                大屏
              </button>
              <button className="btn-ctrl btn-start" onClick={handleStart} disabled={running || (source === 'rtsp' && !selectedCamera) || (source === 'batch' && (batchFiles.length === 0 || batchProcessing))}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21"/></svg>
                开始
              </button>
              <button className="btn-ctrl btn-stop" onClick={handleStop} disabled={!running}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                停止
              </button>
            </div>
          </header>

          {/* Viewer */}
          <div className="viewer">
            <div className="canvas-wrap">
              {systemStatus?.model.status === 'loading' && (
                <div className="model-status-banner" role="status">
                  <span className="model-status-spinner" />
                  模型加载中...
                </div>
              )}
              {systemStatus?.model.status === 'error' && (
                <div className="model-status-banner model-status-error" role="alert" title={systemStatus.model.error}>
                  模型加载失败: {systemStatus.model.error || '请检查模型配置'}
                </div>
              )}
              {sourceError && (
                <div className="model-status-banner model-status-error source-error-banner" role="alert" title={sourceError}>
                  {sourceError}
                </div>
              )}
              {source === 'rtsp' && rtspStreamUrl && (
                <img id="source-image" ref={imageRef} src={rtspStreamUrl} alt="RTSP stream" onLoad={() => setViewerRevision((revision) => revision + 1)} />
              )}
              {source === 'webcam' && (
                <video id="source-video" ref={videoRef} autoPlay playsInline muted onLoadedMetadata={() => setViewerRevision((revision) => revision + 1)} />
              )}
              {source === 'image' && annotatedImage && (
                <img id="source-image" ref={imageRef} src={annotatedImage} alt="Detection result" onLoad={() => setViewerRevision((revision) => revision + 1)} />
              )}
              {source === 'video' && videoFileUrl && (
                <video id="source-video" ref={videoRef} src={videoFileUrl} controls playsInline onLoadedMetadata={() => setViewerRevision((revision) => revision + 1)} />
              )}
              {source === 'batch' && batchItems.length > 0 && (
                <div className="batch-results">
                  <div className="batch-queue-list">
                    {batchItems.map((item, i) => (
                      <div key={`${item.filename}-${i}`} className={`batch-item ${item.status === 'processing' ? 'processing-current' : ''}`}>
                        <span className="batch-item-name" title={item.filename}>{item.filename}</span>
                        <span className={`batch-item-status ${item.status}`}>
                          {item.status === 'pending' ? '等待中' : item.status === 'processing' ? '处理中' : item.status === 'done' ? '完成' : '错误'}
                        </span>
                        {item.status === 'processing' && (
                          <div className="batch-item-spinner" />
                        )}
                        {item.status === 'done' && (
                          <div className="batch-item-counts">
                            {Object.entries(item.detection_summary).map(([cls, count]) => (
                              <span key={cls} className="batch-count-chip">
                                <span className="batch-count-dot" style={{ background: cls === 'phone_use' ? '#ef4444' : cls === 'talking' ? '#3b82f6' : cls === 'sleeping' ? '#eab308' : '#22c55e' }} />
                                {count}
                              </span>
                            ))}
                          </div>
                        )}
                        {item.status === 'done' && (
                          <span className="batch-item-summary">{item.frame_count} 帧 · {item.latency_sec.toFixed(1)}s</span>
                        )}
                        {item.status === 'done' && (
                          <button className="batch-item-view" onClick={() => openPlaybackModal(i)}>查看</button>
                        )}
                        {item.status === 'error' && (
                          <span className="batch-item-summary" title={item.error}>错误</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {source === 'batch' && batchItems.length === 0 && (
                <div id="placeholder" className="placeholder">
                  <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" opacity=".3">
                    <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3v4M8 3v4"/>
                  </svg>
                  <p>在左侧选择多个视频，点击「开始批量检测」</p>
                </div>
              )}
              <canvas id="overlay-canvas" ref={canvasRef} />

              {((source === 'rtsp' && !rtspStreamUrl) || (source === 'webcam' && !running && !loading) || (source === 'image' && !annotatedImage) || (source === 'video' && !videoFileUrl)) && (
                <div id="placeholder" className="placeholder">
                  <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" opacity=".3">
                    <rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>
                  </svg>
                  <p>选择左侧检测源，点击「开始」启动实时检测</p>
                </div>
              )}

              {loading && (
                <div id="loading" className="loading">
                  <div className="spinner" />
                  <p>正在处理...</p>
                </div>
              )}
            </div>

            {/* Stats Bar */}
            <div className="stats-bar">
              <div className="stats-left">
                {Object.entries(displayNames).map(([name, displayName]) => (
                  <div key={name} className="stat-chip" data-class={name}>
                    <span className="stat-dot" style={{ background: name === 'phone_use' ? '#ef4444' : name === 'talking' ? '#3b82f6' : name === 'sleeping' ? '#eab308' : '#22c55e' }} />
                    <span className="stat-name">{displayName}</span>
                    <span className="stat-num">{detections.filter((d) => d.class_name === name).length}</span>
                  </div>
                ))}
              </div>
              <div className="stats-right">
                <div className="stat-metric">
                  <span className="metric-label">延迟</span>
                  <span className="metric-val">{latencyMs !== null ? `${latencyMs.toFixed(0)} ms` : '--'}</span>
                </div>
                <div className="stat-metric">
                  <span className="metric-label">帧数</span>
                  <span className="metric-val">{frameCount}</span>
                </div>
              </div>
            </div>
          </div>
        </main>

        {/* Right Sidebar: Camera List */}
        <aside className="right-sidebar" id="right-sidebar">
          <div className="right-sidebar-header">
            <span className="right-sidebar-title">摄像头</span>
            <div className="cam-actions">
              <button 
                className="cam-action-btn" 
                id="btn-test-cameras" 
                title="测试连通性"
                onClick={handleTestCameras}
                disabled={testingCameras}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              </button>
              <button className="cam-action-btn" id="btn-add-camera" title="添加摄像头" onClick={() => setModalOpen(true)}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              </button>
            </div>
          </div>
          <div className="camera-list" id="camera-list">
            {cameras.length === 0 ? (
              <div className="camera-loading">暂无摄像头，点击 + 添加</div>
            ) : (
              Object.entries(groupedCameras).map(([group, groupCameras]) => (
                <div key={group}>
                  <div className="cam-group-header">
                    <span className="cam-group-toggle">&#9660;</span>
                    <span className="cam-group-title">{getGroupLabel(group)}</span>
                    <span className="cam-group-count">{groupCameras.length}</span>
                  </div>
                  <div className="cam-group-items">
                    {groupCameras.map((camera) => (
                      <div
                        key={camera.ip}
                        data-ip={camera.ip}
                        className={`camera-item ${selectedCamera?.ip === camera.ip ? 'active' : ''} ${camera.group === 'custom' ? 'custom' : ''}`}
                        onClick={() => handleSelectCamera(camera)}
                      >
                        <span className="cam-dot" />
                        <div className="cam-info">
                          {camera.name ? (
                            <>
                              <span className="cam-name">{camera.name}</span>
                              <span className="cam-ip">{camera.ip}</span>
                            </>
                          ) : (
                            <span className="cam-ip-only">{camera.ip}</span>
                          )}
                        </div>
                        <span className={`cam-status ${cameraStatuses[camera.ip] || 'unknown'}`} />
                        <button className="cam-edit" title="编辑" onClick={(e) => { e.stopPropagation(); setEditingCamera(camera); setModalOpen(true) }}>
                          &#9998;
                        </button>
                        <button className="cam-delete" title="删除" onClick={(e) => { e.stopPropagation(); handleDeleteCamera(camera) }}>
                          &times;
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        </aside>
      </div>

      {/* Camera Modal */}
      {modalOpen && (
        <div id="cam-modal" className="cam-modal" onClick={() => { setModalOpen(false); setEditingCamera(null) }}>
          <div className="cam-modal-backdrop" />
          <div className="cam-modal-dialog settings-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="cam-modal-header">
              <span id="cam-modal-title">{editingCamera ? '编辑摄像头' : '添加摄像头'}</span>
              <button className="cam-modal-close" onClick={() => { setModalOpen(false); setEditingCamera(null) }}>&times;</button>
            </div>
            <div className="cam-modal-body">
              <h3 className="settings-section-title">摄像头连接</h3>
              <div className="cam-field">
                <label>IP 地址 <span className="required">*</span></label>
                <input type="text" id="cam-ip" placeholder="192.168.1.100" defaultValue={editingCamera?.ip || ''} disabled={!!editingCamera} style={editingCamera ? { opacity: 0.5 } : {}} />
              </div>
              <div className="cam-field">
                <label>别名</label>
                <input type="text" id="cam-name" placeholder="如：教室A前摄像头" defaultValue={editingCamera?.name || ''} />
              </div>
              <div className="cam-field">
                <label>备注</label>
                <input type="text" id="cam-note" placeholder="教室名称或位置描述" defaultValue={editingCamera?.note || ''} />
              </div>
            </div>
            <div className="cam-modal-footer">
              <button className="cam-btn cam-btn-cancel" onClick={() => { setModalOpen(false); setEditingCamera(null) }}>取消</button>
              <button className="cam-btn cam-btn-save" onClick={async () => {
                const ip = (document.getElementById('cam-ip') as HTMLInputElement)?.value
                const name = (document.getElementById('cam-name') as HTMLInputElement)?.value
                const note = (document.getElementById('cam-note') as HTMLInputElement)?.value
                if (!ip) {
                  alert('IP 地址不能为空')
                  return
                }
                try {
                  if (editingCamera) {
                    await updateCamera(editingCamera.ip, { name: name || '', note: note || undefined })
                  } else {
                    await addCamera({ ip, name: name || '', note: note || undefined })
                  }
                  setModalOpen(false)
                  setEditingCamera(null)
                  loadCameras()
                } catch (err) {
                  alert(err instanceof Error ? err.message : '保存失败')
                }
              }}>保存</button>
            </div>
          </div>
        </div>
      )}

      {/* Playback Modal */}
      {playbackModalOpen && playbackItem && (
        <div id="playback-modal" className="playback-modal" onClick={closePlaybackModal}>
          <div className="playback-container" onClick={e => e.stopPropagation()}>
            <div className="playback-header">
              <span className="playback-title">{playbackItem.filename}</span>
              <button className="playback-close" onClick={closePlaybackModal}>&times;</button>
            </div>
            <div className="playback-body">
              <div className="playback-viewer">
                <video id="playback-video" playsInline controls />
                <canvas id="playback-canvas" />
              </div>
              <div className="playback-stats">
                {Object.entries(playbackItem.detection_summary || {}).map(([cls, count]) => (
                  <div key={cls} className="playback-stat-chip">
                    <span className="playback-stat-dot" style={{background: cls === 'phone_use' ? '#ef4444' : cls === 'talking' ? '#3b82f6' : cls === 'sleeping' ? '#eab308' : '#22c55e'}} />
                    <span className="playback-stat-name">{displayNames[cls]}</span>
                    <span className="playback-stat-num">{count as number}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {settingsModalOpen && (
        <div className="cam-modal" onClick={() => setSettingsModalOpen(false)}>
          <div className="cam-modal-backdrop" />
          <div className="cam-modal-dialog settings-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="cam-modal-header">
              <span>设置</span>
              <button className="cam-modal-close" onClick={() => setSettingsModalOpen(false)}>&times;</button>
            </div>
            <div className="cam-modal-body">
              <div className="cam-field">
                <label>RTSP 用户名</label>
                <input type="text" value={rtspCredentials.username} onChange={(e) => setRtspCredentials(prev => ({ ...prev, username: e.target.value }))} />
              </div>
              <div className="cam-field">
                <label>RTSP 密码</label>
                <input type="password" value={rtspCredentials.password} onChange={(e) => setRtspCredentials(prev => ({ ...prev, password: e.target.value }))} />
              </div>
              <div className="cam-field">
                <label>RTSP 端口</label>
                <input type="number" value={rtspCredentials.port} onChange={(e) => setRtspCredentials(prev => ({ ...prev, port: parseInt(e.target.value) || 554 }))} />
              </div>
              <h3 className="settings-section-title">大模型分析</h3>
              <div className="cam-field">
                <label>OpenAI 兼容 Base URL</label>
                <input type="url" value={llmForm.base_url} placeholder="https://api.openai.com/v1" onChange={(e) => setLlmForm(prev => ({ ...prev, base_url: e.target.value }))} />
              </div>
              <div className="cam-form-row">
                <div className="cam-field">
                  <label>模型</label>
                  <input type="text" value={llmForm.model} onChange={(e) => setLlmForm(prev => ({ ...prev, model: e.target.value }))} />
                </div>
                <div className="cam-field settings-timeout">
                  <label>超时 (秒)</label>
                  <input type="number" min="1" max="300" value={llmForm.timeout} onChange={(e) => setLlmForm(prev => ({ ...prev, timeout: Number(e.target.value) || 60 }))} />
                </div>
              </div>
              <div className="cam-field">
                <label>API Key {llmSettings?.has_api_key ? `(${llmSettings.api_key_masked})` : ''}</label>
                <input type="password" value={llmForm.api_key} placeholder={llmSettings?.has_api_key ? '留空则保留现有密钥' : '可选，本地服务通常无需密钥'} onChange={(e) => setLlmForm(prev => ({ ...prev, api_key: e.target.value }))} />
              </div>
              <div className="settings-inline-actions">
                <button className="cam-btn cam-btn-cancel" disabled={llmTesting || !llmSettings?.model} onClick={handleTestLlm}>测试连接</button>
                <button className="cam-btn cam-btn-save" disabled={llmSaving || !llmForm.base_url || !llmForm.model} onClick={handleSaveLlm}>{llmSaving ? '保存中...' : '保存大模型设置'}</button>
              </div>
              {llmTestMessage && <div className="settings-status" role="status">{llmTestMessage}</div>}
              <h3 className="settings-section-title">摄像头导入</h3>
              <div className="cam-field">
                <label>批量导入摄像头 (CSV)</label>
                <label className="upload-zone upload-zone-sm" style={{ cursor: 'pointer', marginTop: '4px' }}>
                  <input type="file" accept=".csv" onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) handleImportCsv(file)
                    e.target.value = ''
                  }} />
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                  <span>选择 CSV 文件</span>
                </label>
              </div>
            </div>
            <div className="cam-modal-footer">
              <button className="cam-btn cam-btn-cancel" onClick={() => setSettingsModalOpen(false)}>取消</button>
              <button className="cam-btn cam-btn-save" onClick={handleSaveRtspCredentials}>保存摄像头设置</button>
            </div>
          </div>
        </div>
      )}

      {/* File List Panel */}
      <div id="file-panel" className={`file-panel ${filePanelOpen ? 'open' : ''}`}>
        <div className="file-panel-header">
          <div className="file-panel-tabs">
            <button
              className={`file-tab ${filePanelTab === 'image' ? 'active' : ''}`}
              onClick={() => setFilePanelTab('image')}
            >图片</button>
            <button
              className={`file-tab ${filePanelTab === 'video' ? 'active' : ''}`}
              onClick={() => setFilePanelTab('video')}
            >视频</button>
            <span className="file-panel-count">
              {fileList.filter(f => f.type === filePanelTab).length}
            </span>
          </div>
          <div className="file-panel-header-actions">
            <button
              className={`file-panel-action-btn ${selectionMode ? 'active' : ''}`}
              onClick={() => setSelectionMode(!selectionMode)}
              title="选择"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="9 11 12 14 22 4"/>
                <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
              </svg>
            </button>
            <button
              className="file-panel-action-btn"
              onClick={clearAllFiles}
              title="清空"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
              </svg>
            </button>
            <button
              className="file-panel-close"
              onClick={() => setFilePanelOpen(false)}
            >&times;</button>
          </div>
        </div>
        <div className="file-panel-body" id="file-panel-body">
          {fileList.filter(f => f.type === filePanelTab).length === 0 ? (
            <div className="file-panel-empty">
              暂无{filePanelTab === 'video' ? '视频' : '图片'}文件
            </div>
          ) : (
            <div className="file-grid">
              {fileList.filter(f => f.type === filePanelTab).map(entry => (
                <div
                  key={entry.id}
                  className={`file-card ${activeFileId === entry.id ? 'active' : ''}`}
                  onClick={() => {
                    if (selectionMode) {
                      setFileList(prev => prev.map(f =>
                        f.id === entry.id ? { ...f, selected: !f.selected } : f
                      ))
                    } else {
                      setActiveFileId(entry.id)
                    }
                  }}
                >
                  <div className="file-card-thumb">
                    <input
                      type="checkbox"
                      className="file-card-checkbox"
                      checked={entry.selected}
                      tabIndex={-1}
                      aria-hidden="true"
                      style={{ pointerEvents: 'none' }}
                      readOnly
                    />
                    <img src={entry.thumbnailUrl} alt="" />
                  </div>
                  <button
                    className="file-card-remove"
                    onClick={(e) => { e.stopPropagation(); removeFile(entry.id) }}
                  >&times;</button>
                  <button
                    className="file-card-detect"
                    title="检测"
                    disabled={entry.status === 'detecting'}
                    onClick={(e) => { e.stopPropagation(); handleDetectFile(entry.id) }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21"/></svg>
                  </button>
                  <div className="file-card-info">
                    <div className="file-card-name" title={entry.name}>{entry.name}</div>
                    <div className="file-card-meta">
                      <span>{(entry.size / 1024).toFixed(1)} KB</span>
                      <span className={`file-card-status ${entry.status}`}>{entry.status}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div
        className={`file-panel-overlay ${filePanelOpen ? '' : 'hidden'}`}
        onClick={() => setFilePanelOpen(false)}
      />
      </>} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
