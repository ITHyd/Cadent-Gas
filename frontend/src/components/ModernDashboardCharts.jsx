import React from 'react';

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

const polarToCartesian = (cx, cy, r, angleDeg) => {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180;
  return {
    x: cx + r * Math.cos(angleRad),
    y: cy + r * Math.sin(angleRad),
  };
};

const describeArc = (cx, cy, r, startAngle, endAngle) => {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`;
};

export const DateRangeSelector = ({
  value,
  onChange,
  customStart,
  customEnd,
  onCustomStartChange,
  onCustomEndChange,
  options = [
    { id: '7d', label: '7D' },
    { id: '30d', label: '30D' },
    { id: '90d', label: '90D' },
    { id: 'custom', label: 'Custom' },
  ],
}) => (
  <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
    <div className="segmented" style={{ marginBottom: 0 }}>
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          className={`segment-btn ${value === option.id ? 'active' : ''}`}
          onClick={() => onChange(option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
    {value === 'custom' && (
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="date"
          className="input-control"
          value={customStart}
          onChange={(event) => onCustomStartChange(event.target.value)}
          style={{ minHeight: '36px', width: '160px' }}
        />
        <span style={{ color: '#64748b', fontSize: '0.82rem', fontWeight: 700 }}>to</span>
        <input
          type="date"
          className="input-control"
          value={customEnd}
          onChange={(event) => onCustomEndChange(event.target.value)}
          style={{ minHeight: '36px', width: '160px' }}
        />
      </div>
    )}
  </div>
);

export const TrendBadge = ({ delta = 0, label }) => {
  const positive = delta >= 0;
  const color = positive ? '#047857' : '#b91c1c';
  const bg = positive ? '#ecfdf5' : '#fef2f2';

  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '4px 10px',
      borderRadius: '999px',
      background: bg,
      color,
      border: `1px solid ${color}22`,
      fontSize: '0.76rem',
      fontWeight: 800,
    }}>
      <span>{positive ? '↑' : '↓'}</span>
      <span>{Math.abs(delta)}%</span>
      {label ? <span style={{ color: '#64748b' }}>{label}</span> : null}
    </div>
  );
};

export const DonutChart = ({ segments, size = 210, strokeWidth = 22, centerLabel, centerValue }) => {
  const radius = (size - strokeWidth) / 2;
  const center = size / 2;
  const total = segments.reduce((sum, segment) => sum + (segment.value || 0), 0);
  let startAngle = 0;

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={center} cy={center} r={radius} fill="none" stroke="#e2e8f0" strokeWidth={strokeWidth} />
        {segments.map((segment) => {
          const sweep = total > 0 ? (segment.value / total) * 359.999 : 0;
          const endAngle = startAngle + sweep;
          const path = describeArc(center, center, radius, startAngle, endAngle);
          const currentStart = startAngle;
          startAngle = endAngle;
          if (segment.value <= 0) return null;
          return (
            <path
              key={`${segment.label}-${currentStart}`}
              d={path}
              fill="none"
              stroke={segment.color}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              style={{ transition: 'all 300ms ease' }}
            />
          );
        })}
        <circle cx={center} cy={center} r={radius - strokeWidth / 1.6} fill="#fff" />
        <text x={center} y={center - 6} textAnchor="middle" style={{ fill: '#64748b', fontSize: '12px', fontWeight: 700 }}>
          {centerLabel}
        </text>
        <text x={center} y={center + 18} textAnchor="middle" style={{ fill: '#0f172a', fontSize: '26px', fontWeight: 800 }}>
          {centerValue}
        </text>
      </svg>
    </div>
  );
};

export const LineTrendChart = ({ labels, series, height = 220 }) => {
  const width = 520;
  const padding = { top: 18, right: 18, bottom: 28, left: 28 };
  const values = series.flatMap((item) => item.values || []);
  const maxValue = Math.max(...values, 1);
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  const pointFor = (index, value, totalPoints) => {
    const x = padding.left + (totalPoints <= 1 ? innerWidth / 2 : (index / (totalPoints - 1)) * innerWidth);
    const y = padding.top + innerHeight - (value / maxValue) * innerHeight;
    return { x, y };
  };

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: 'block' }}>
      {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
        const y = padding.top + innerHeight - tick * innerHeight;
        return (
          <g key={tick}>
            <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#e2e8f0" strokeDasharray="4 6" />
            <text x={8} y={y + 4} fill="#94a3b8" fontSize="11">{Math.round(maxValue * tick)}</text>
          </g>
        );
      })}

      {series.map((item) => {
        const points = (item.values || []).map((value, index) => pointFor(index, value, item.values.length));
        const path = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
        return (
          <g key={item.label}>
            <path d={path} fill="none" stroke={item.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
            {points.map((point, index) => (
              <circle key={`${item.label}-${index}`} cx={point.x} cy={point.y} r="4.5" fill="#fff" stroke={item.color} strokeWidth="2.5" />
            ))}
          </g>
        );
      })}

      {labels.map((label, index) => {
        const x = padding.left + (labels.length <= 1 ? innerWidth / 2 : (index / (labels.length - 1)) * innerWidth);
        return (
          <text key={label} x={x} y={height - 8} textAnchor="middle" fill="#64748b" fontSize="11">
            {label}
          </text>
        );
      })}
    </svg>
  );
};

export const FunnelChart = ({ steps, height = 240 }) => {
  const width = 520;
  const maxValue = Math.max(...steps.map((step) => step.value || 0), 1);
  const stepHeight = height / Math.max(steps.length, 1);
  const labelWidth = 150;
  const valueWidth = 48;
  const gutter = 18;
  const chartLeft = labelWidth + gutter;
  const chartRight = width - valueWidth - gutter;
  const chartWidth = chartRight - chartLeft;

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: 'block' }}>
      {steps.map((step, index) => {
        const topWidth = step.value > 0 ? clamp((step.value / maxValue) * chartWidth, 16, chartWidth) : 0;
        const bottomWidth = step.value > 0 ? Math.max(12, topWidth * 0.82) : 0;
        const y = index * stepHeight;
        const xTop = chartLeft + (chartWidth - topWidth) / 2;
        const xBottom = chartLeft + (chartWidth - bottomWidth) / 2;
        const points = [
          `${xTop},${y + 8}`,
          `${xTop + topWidth},${y + 8}`,
          `${xBottom + bottomWidth},${y + stepHeight - 8}`,
          `${xBottom},${y + stepHeight - 8}`,
        ].join(' ');
        return (
          <g key={step.label}>
            {step.value > 0 ? <polygon points={points} fill={step.color} opacity="0.92" /> : null}
            <text x={18} y={y + stepHeight / 2 - 4} fill="#0f172a" fontSize="12" fontWeight="800">{step.label}</text>
            <text x={18} y={y + stepHeight / 2 + 14} fill="#64748b" fontSize="11">{step.subLabel}</text>
            <text x={width - 12} y={y + stepHeight / 2 + 4} textAnchor="end" fill="#0f172a" fontSize="14" fontWeight="800">{step.value}</text>
          </g>
        );
      })}
    </svg>
  );
};

export const HeatmapChart = ({ rows, columns, values, colorForValue }) => (
  <div style={{ display: 'grid', gridTemplateColumns: `120px repeat(${columns.length}, minmax(0, 1fr))`, gap: '8px', alignItems: 'stretch' }}>
    <div />
    {columns.map((column) => (
      <div key={column} style={{ fontSize: '0.72rem', fontWeight: 800, color: '#64748b', textAlign: 'center' }}>
        {column}
      </div>
    ))}
    {rows.map((row) => (
      <React.Fragment key={row}>
        <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#0f172a', display: 'flex', alignItems: 'center' }}>{row}</div>
        {columns.map((column) => {
          const value = values?.[row]?.[column] || 0;
          const meta = colorForValue(row, value);
          return (
            <div
              key={`${row}-${column}`}
              style={{
                minHeight: '54px',
                borderRadius: '14px',
                background: meta.background,
                border: `1px solid ${meta.border}`,
                color: meta.color,
                display: 'grid',
                placeItems: 'center',
                textAlign: 'center',
                padding: '8px',
              }}
            >
              <div>
                <div style={{ fontSize: '1rem', fontWeight: 800 }}>{value}</div>
                <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#475569' }}>{meta.label}</div>
              </div>
            </div>
          );
        })}
      </React.Fragment>
    ))}
  </div>
);

export const BubbleChart = ({ points, height = 320 }) => {
  const width = 560;
  const padding = { top: 20, right: 24, bottom: 44, left: 44 };
  const maxX = Math.max(...points.map((point) => point.x || 0), 1);
  const maxY = Math.max(...points.map((point) => point.y || 0), 1);
  const maxSize = Math.max(...points.map((point) => point.size || 0), 1);
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: 'block' }}>
      <line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} stroke="#cbd5e1" />
      <line x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} stroke="#cbd5e1" />

      {points.map((point) => {
        const x = padding.left + ((point.x || 0) / maxX) * innerWidth;
        const y = padding.top + innerHeight - ((point.y || 0) / maxY) * innerHeight;
        const r = 12 + ((point.size || 0) / maxSize) * 28;
        return (
          <g key={point.id}>
            <circle cx={x} cy={y} r={r} fill={point.color} opacity="0.78" stroke="#fff" strokeWidth="2" />
            <text x={x} y={y + 4} textAnchor="middle" fill="#0f172a" fontSize="10" fontWeight="800">
              {point.shortLabel}
            </text>
          </g>
        );
      })}

      <text x={width / 2} y={height - 10} textAnchor="middle" fill="#64748b" fontSize="12" fontWeight="700">Workflow count</text>
      <text x={16} y={height / 2} textAnchor="middle" fill="#64748b" fontSize="12" fontWeight="700" transform={`rotate(-90 16 ${height / 2})`}>
        False KB ratio
      </text>
    </svg>
  );
};
