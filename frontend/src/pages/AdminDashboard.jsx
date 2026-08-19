import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { HBarChart, LineChart } from '../components/Charts'
import { Alert, STAGE_COLOR, Spinner, rupees } from '../components/common'

function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

export default function AdminDashboard() {
  const [data, setData] = useState(null)
  const [aiHealth, setAiHealth] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [dashboard, health] = await Promise.all([
        api.dashboard(),
        api.aiHealth().catch(() => null),
      ])
      setData(dashboard)
      setAiHealth(health)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(load, 15000)
    return () => clearInterval(timer)
  }, [load])

  if (error && !data) return <Alert>{error}</Alert>
  if (!data) {
    return (
      <div className="empty">
        <Spinner /> Loading dashboard…
      </div>
    )
  }

  const statusData = data.orders_by_status.map((s) => ({ label: s.status, value: s.count }))
  const popularData = data.popular_items.map((p) => ({ label: p.name, value: p.units_sold }))
  const revenueData = data.popular_items.map((p) => ({ label: p.name, value: p.revenue }))
  const hourPoints = data.revenue_by_hour.map((p) => ({
    label: p.hour,
    value: p.revenue,
    orders: p.orders,
  }))

  return (
    <>
      <div className="section-head">
        <div>
          <h1>Dashboard</h1>
          <p>Last 24 hours, refreshed every 15 seconds.</p>
        </div>
        <div className="row">
          {aiHealth && (
            <span className={`mode-badge ${aiHealth.reachable ? 'live' : 'degraded'}`}>
              AI search: {aiHealth.reachable ? 'live' : 'fallback mode'}
            </span>
          )}
          <button type="button" className="btn btn-ghost btn-sm" onClick={load}>
            Refresh
          </button>
        </div>
      </div>

      <Alert>{error}</Alert>

      <div className="stat-row">
        <Stat
          label="Revenue last 24h"
          value={rupees(data.revenue_today)}
          sub="Confirmed orders onward; cancellations excluded"
        />
        <Stat label="Orders last 24h" value={data.orders_today} sub="Excluding cancelled" />
        <Stat label="Average order" value={rupees(data.average_order_value)} sub="Per paying order" />
        <Stat
          label="Active now"
          value={data.active_orders}
          sub="Not yet picked up or cancelled"
        />
      </div>

      <div className="chart-grid">
        <section className="card card-pad">
          <div className="chart-title">Orders by status</div>
          <p className="chart-note">
            All orders. Colour follows the stage's position in the workflow, so the ramp
            darkens as an order progresses.
          </p>
          <div className="mt">
            <HBarChart
              data={statusData}
              color={(d) => STAGE_COLOR[d.label] ?? 'var(--accent)'}
              emptyText="No orders yet."
            />
          </div>
        </section>

        <section className="card card-pad">
          <div className="chart-title">Revenue by hour</div>
          <p className="chart-note">Rolling 24-hour confirmed revenue, hour by hour.</p>
          <div className="mt">
            <LineChart points={hourPoints} emptyText="No revenue recorded in the last 24 hours yet." />
          </div>
        </section>

        <section className="card card-pad">
          <div className="chart-title">Popular items — units sold</div>
          <p className="chart-note">Top dishes by quantity in the last 24 hours.</p>
          <div className="mt">
            <HBarChart data={popularData} emptyText="No items sold in the last 24 hours yet." />
          </div>
        </section>

        <section className="card card-pad">
          <div className="chart-title">Popular items — revenue</div>
          <p className="chart-note">
            Same dishes by rupee contribution. Units and revenue rank differently, which is
            the point of showing both.
          </p>
          <div className="mt">
            <HBarChart data={revenueData} valueFormat={rupees} emptyText="No revenue in the last 24 hours yet." />
          </div>
        </section>
      </div>
    </>
  )
}
