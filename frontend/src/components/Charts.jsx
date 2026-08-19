import { useMemo, useState } from 'react'
import { rupees } from './common'

/**
 * Hand-rolled SVG charts rather than a charting library.
 *
 * Three reasons: no extra dependency to install on the demo machine, full
 * control over the mark specs (thin marks, rounded data-ends anchored to
 * the baseline, 2px lines, recessive grid), and a table view alongside each
 * chart so the numbers are never encoded in colour alone.
 */

/** Horizontal bars. `color` may be a function of the datum for an ordinal ramp. */
export function HBarChart({ data, valueFormat = (v) => v, color = 'var(--accent)', emptyText }) {
  const [showTable, setShowTable] = useState(false)
  const max = Math.max(1, ...data.map((d) => d.value))

  if (!data.length) return <p className="muted small">{emptyText}</p>

  return (
    <div>
      {!showTable &&
        data.map((datum) => {
          const pct = (datum.value / max) * 100
          const fill = typeof color === 'function' ? color(datum) : color
          return (
            <div className="hbar-row" key={datum.label} title={`${datum.label}: ${valueFormat(datum.value)}`}>
              <span className="hbar-label">{datum.label}</span>
              <div className="hbar-track">
                <svg width="100%" height="14" role="img" aria-label={`${datum.label}: ${valueFormat(datum.value)}`}>
                  <rect x="0" y="4" width="100%" height="6" rx="3" fill="var(--surface-2)" />
                  {datum.value > 0 && (
                    <rect
                      x="0"
                      y="4"
                      width={`${Math.max(pct, 1.5)}%`}
                      height="6"
                      rx="3"
                      fill={fill}
                    />
                  )}
                </svg>
              </div>
              <span className="hbar-value">{valueFormat(datum.value)}</span>
            </div>
          )
        })}

      {showTable && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Label</th>
                <th className="num">Value</th>
              </tr>
            </thead>
            <tbody>
              {data.map((datum) => (
                <tr key={datum.label}>
                  <td>{datum.label}</td>
                  <td className="num">{valueFormat(datum.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <button type="button" className="btn btn-sm btn-ghost mt" onClick={() => setShowTable((v) => !v)}>
        {showTable ? 'Show chart' : 'Show table'}
      </button>
    </div>
  )
}

/** Single-series line chart with a hover crosshair and tooltip. */
export function LineChart({ points, emptyText }) {
  const [hover, setHover] = useState(null)
  const [showTable, setShowTable] = useState(false)

  const width = 520
  const height = 170
  const padding = { top: 14, right: 14, bottom: 26, left: 46 }

  const geometry = useMemo(() => {
    if (points.length === 0) return null
    const max = Math.max(1, ...points.map((p) => p.value))
    const innerW = width - padding.left - padding.right
    const innerH = height - padding.top - padding.bottom
    const step = points.length > 1 ? innerW / (points.length - 1) : 0
    const coords = points.map((point, index) => ({
      ...point,
      x: padding.left + (points.length > 1 ? index * step : innerW / 2),
      y: padding.top + innerH - (point.value / max) * innerH,
    }))
    return { max, innerH, coords }
  }, [points])

  if (!points.length) return <p className="muted small">{emptyText}</p>

  const { max, coords } = geometry
  const line = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ')
  const area = `${padding.left},${height - padding.bottom} ${line} ${
    coords[coords.length - 1].x
  },${height - padding.bottom}`

  const gridValues = [0, 0.5, 1].map((f) => max * f)

  return (
    <div>
      {!showTable && (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          preserveAspectRatio="xMidYMid meet"
          style={{ display: 'block', height: 'auto' }}
          role="img"
          aria-label="Revenue by hour"
          onMouseLeave={() => setHover(null)}
        >
          {gridValues.map((value, index) => {
            const y = padding.top + (height - padding.top - padding.bottom) * (1 - index / 2)
            return (
              <g key={value}>
                <line
                  x1={padding.left}
                  x2={width - padding.right}
                  y1={y}
                  y2={y}
                  stroke="var(--border)"
                  strokeWidth="1"
                />
                <text x={padding.left - 8} y={y + 3} textAnchor="end" fontSize="9" fill="var(--text-muted)">
                  {value >= 1000 ? `${Math.round(value / 1000)}k` : Math.round(value)}
                </text>
              </g>
            )
          })}

          <polygon points={area} fill="var(--accent)" opacity="0.10" />
          <polyline
            points={line}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {coords.map((c) => (
            <g key={c.label}>
              {/* generous invisible hit target, per interaction spec */}
              <rect
                x={c.x - 14}
                y={padding.top}
                width="28"
                height={height - padding.top - padding.bottom}
                fill="transparent"
                onMouseEnter={() => setHover(c)}
              />
              <circle
                cx={c.x}
                cy={c.y}
                r={hover?.label === c.label ? 5 : 3.5}
                fill="var(--accent)"
                stroke="var(--surface-1)"
                strokeWidth="2"
              />
            </g>
          ))}

          {hover && (
            <g pointerEvents="none">
              <line
                x1={hover.x}
                x2={hover.x}
                y1={padding.top}
                y2={height - padding.bottom}
                stroke="var(--border-strong)"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <rect
                x={Math.min(Math.max(hover.x - 52, 2), width - 106)}
                y={padding.top - 4}
                width="104"
                height="34"
                rx="6"
                fill="var(--surface-1)"
                stroke="var(--border-strong)"
              />
              <text
                x={Math.min(Math.max(hover.x - 52, 2), width - 106) + 10}
                y={padding.top + 9}
                fontSize="10"
                fill="var(--text-secondary)"
              >
                {hover.label}
              </text>
              <text
                x={Math.min(Math.max(hover.x - 52, 2), width - 106) + 10}
                y={padding.top + 23}
                fontSize="12"
                fontWeight="650"
                fill="var(--text-primary)"
              >
                {rupees(hover.value)} · {hover.orders} orders
              </text>
            </g>
          )}

          {coords.map((c, index) =>
            index % Math.ceil(coords.length / 6 || 1) === 0 ? (
              <text
                key={`x-${c.label}`}
                x={c.x}
                y={height - padding.bottom + 14}
                textAnchor="middle"
                fontSize="9"
                fill="var(--text-muted)"
              >
                {c.label}
              </text>
            ) : null,
          )}
        </svg>
      )}

      {showTable && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Hour</th>
                <th className="num">Revenue</th>
                <th className="num">Orders</th>
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr key={point.label}>
                  <td>{point.label}</td>
                  <td className="num">{rupees(point.value)}</td>
                  <td className="num">{point.orders}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <button type="button" className="btn btn-sm btn-ghost mt" onClick={() => setShowTable((v) => !v)}>
        {showTable ? 'Show chart' : 'Show table'}
      </button>
    </div>
  )
}
