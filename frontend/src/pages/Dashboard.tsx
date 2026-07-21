import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Chart as ChartJS, ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement, PointElement, LineElement, Filler } from 'chart.js'
import { Doughnut, Bar, Line } from 'react-chartjs-2'
import type { DashboardStats, DashboardCamera, DisplayNames, HistoryEntry } from '../types'
import { getDashboardStats, getDashboardHistory, getDisplayNames, downloadDashboardReport } from '../api/client'
import '../dashboard.css'

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement, PointElement, LineElement, Filler)

const COLORS: Record<string, string> = {
  phone_use: '#ef4444',
  talking: '#3b82f6',
  sleeping: '#eab308',
  standing: '#22c55e',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [displayNames, setDisplayNames] = useState<DisplayNames>({})
  const [history, setHistory] = useState<Record<string, HistoryEntry[]>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      getDisplayNames(),
      getDashboardStats(),
      getDashboardHistory(),
    ]).then(([names, s, h]) => {
      setDisplayNames(names)
      setStats(s)
      setHistory(h.history)
    }).catch(console.error).finally(() => setLoading(false))
  }, [])

  const classKeys = ['phone_use', 'talking', 'sleeping', 'standing']
  const totalDetections = stats ? Object.values(stats.total).reduce((a, b) => a + b, 0) : 0

  const donutData = {
    labels: classKeys.map(k => displayNames[k] || k),
    datasets: [{
      data: classKeys.map(k => stats?.total[k] || 0),
      backgroundColor: classKeys.map(k => COLORS[k]),
      borderColor: 'var(--bg-surface)',
      borderWidth: 2,
    }],
  }

  const donutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom' as const, labels: { color: '#94a3b8', padding: 16, usePointStyle: true, pointStyleWidth: 10 } },
    },
    cutout: '65%',
  }

  const barData = {
    labels: (stats?.cameras || []).map(c => c.name || c.ip),
    datasets: classKeys.map(key => ({
      label: displayNames[key] || key,
      data: (stats?.cameras || []).map(c => c.stats[key] || 0),
      backgroundColor: COLORS[key],
      borderRadius: 3,
    })),
  }

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom' as const, labels: { color: '#94a3b8', padding: 12, usePointStyle: true, pointStyleWidth: 10 } },
    },
    scales: {
      x: { stacked: true, grid: { color: '#1e293b' }, ticks: { color: '#64748b', font: { size: 11 } } },
      y: { stacked: true, grid: { color: '#1e293b' }, ticks: { color: '#64748b' } },
    },
  }

  const lineData = (() => {
    const firstCam = Object.keys(history)[0]
    if (!firstCam) return { labels: [], datasets: [] }
    const entries = history[firstCam] || []
    return {
      labels: entries.map(e => {
        const d = new Date(e.time)
        return `${d.getHours().toString().padStart(2, '0')}:00`
      }),
      datasets: classKeys.map(key => ({
        label: displayNames[key] || key,
        data: entries.map(e => (e as unknown as Record<string, number>)[key] || 0),
        borderColor: COLORS[key],
        backgroundColor: COLORS[key] + '20',
        fill: true,
        tension: 0.4,
        pointRadius: 2,
        pointHoverRadius: 5,
      })),
    }
  })()

  const lineOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom' as const, labels: { color: '#94a3b8', padding: 12, usePointStyle: true, pointStyleWidth: 10 } },
    },
    scales: {
      x: { grid: { color: '#1e293b' }, ticks: { color: '#64748b', font: { size: 11 } } },
      y: { grid: { color: '#1e293b' }, ticks: { color: '#64748b' }, beginAtZero: true },
    },
  }

  if (loading) {
    return (
      <div className="dashboard-page">
        <div className="dashboard-loading">
          <div className="spinner" />
          <p>加载中...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <div className="dashboard-header-left">
          <button className="btn-back" onClick={() => navigate('/')}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            返回
          </button>
          <h1>监控大屏</h1>
        </div>
        <button className="btn-report" onClick={() => downloadDashboardReport()}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          导出报告
        </button>
      </header>

      <div className="dashboard-body">
        {/* Summary cards */}
        <div className="dashboard-summary">
          <div className="summary-card">
            <div className="summary-icon" style={{ background: 'rgba(99,102,241,.15)', color: '#818cf8' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
            </div>
            <div className="summary-info">
              <span className="summary-val">{stats?.total_cameras || 0}</span>
              <span className="summary-label">摄像头总数</span>
            </div>
          </div>
          <div className="summary-card">
            <div className="summary-icon" style={{ background: 'rgba(16,185,129,.15)', color: '#10b981' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            </div>
            <div className="summary-info">
              <span className="summary-val">{stats?.online_count || 0}</span>
              <span className="summary-label">在线摄像头</span>
            </div>
          </div>
          <div className="summary-card">
            <div className="summary-icon" style={{ background: 'rgba(6,182,212,.15)', color: '#06b6d4' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><circle cx="12" cy="10" r="4"/></svg>
            </div>
            <div className="summary-info">
              <span className="summary-val">{totalDetections}</span>
              <span className="summary-label">总检测次数</span>
            </div>
          </div>
          {classKeys.map(key => (
            <div key={key} className="summary-card">
              <div className="summary-icon" style={{ background: COLORS[key] + '20', color: COLORS[key] }}>
                <span className="summary-dot" style={{ background: COLORS[key] }} />
              </div>
              <div className="summary-info">
                <span className="summary-val">{stats?.total[key] || 0}</span>
                <span className="summary-label">{displayNames[key] || key}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Charts row */}
        <div className="dashboard-charts">
          <div className="chart-card">
            <h3 className="chart-title">行为分布</h3>
            <div className="chart-body" style={{ height: 280 }}>
              <Doughnut data={donutData} options={donutOptions} />
            </div>
          </div>
          <div className="chart-card chart-card-wide">
            <h3 className="chart-title">各摄像头检测统计</h3>
            <div className="chart-body" style={{ height: 280 }}>
              {(stats?.cameras || []).length > 0 ? (
                <Bar data={barData} options={barOptions} />
              ) : (
                <div className="chart-empty">暂无摄像头数据</div>
              )}
            </div>
          </div>
        </div>

        {/* Trend chart */}
        <div className="dashboard-trend">
          <div className="chart-card">
            <h3 className="chart-title">24 小时趋势</h3>
            <div className="chart-body" style={{ height: 260 }}>
              {Object.keys(history).length > 0 ? (
                <Line data={lineData} options={lineOptions} />
              ) : (
                <div className="chart-empty">暂无历史数据</div>
              )}
            </div>
          </div>
        </div>

        {/* Camera grid */}
        <div className="dashboard-cameras">
          <h3 className="section-title">摄像头状态</h3>
          <div className="camera-grid">
            {(stats?.cameras || []).map((cam: DashboardCamera) => (
              <div key={cam.ip} className={`cam-card ${cam.online ? 'online' : 'offline'}`}>
                <div className="cam-card-header">
                  <span className="cam-card-dot" />
                  <span className="cam-card-name">{cam.name || cam.ip}</span>
                  <span className="cam-card-badge">{cam.online ? '在线' : '离线'}</span>
                </div>
                <div className="cam-card-stats">
                  {classKeys.map(key => (
                    <div key={key} className="cam-stat-row">
                      <span className="cam-stat-dot" style={{ background: COLORS[key] }} />
                      <span className="cam-stat-name">{displayNames[key] || key}</span>
                      <span className="cam-stat-val">{cam.stats[key] || 0}</span>
                    </div>
                  ))}
                </div>
                {cam.last_update && (
                  <div className="cam-card-time">最后更新: {new Date(cam.last_update).toLocaleTimeString()}</div>
                )}
              </div>
            ))}
            {(stats?.cameras || []).length === 0 && (
              <div className="cam-card-empty">暂无摄像头，请先添加摄像头</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
