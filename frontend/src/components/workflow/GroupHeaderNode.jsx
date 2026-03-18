import { Handle, Position } from 'reactflow';

const GROUP_COLORS = {
  'FireAngel': { bg: '#eff6ff', border: '#3b82f6', dot: '#3b82f6' },
  'Firehawk': { bg: '#f0fdf4', border: '#22c55e', dot: '#22c55e' },
  'Aico': { bg: '#fffbeb', border: '#f59e0b', dot: '#f59e0b' },
  'Kidde': { bg: '#fef2f2', border: '#ef4444', dot: '#ef4444' },
  'X-Sense': { bg: '#faf5ff', border: '#8b5cf6', dot: '#8b5cf6' },
  'Other': { bg: '#f8fafc', border: '#94a3b8', dot: '#94a3b8' },
};

const GroupHeaderNode = ({ data, selected }) => {
  const group = data.groupName || 'Group';
  const nodeCount = data.nodeCount || 0;
  const isExpanded = data.isExpanded || false;
  const colors = GROUP_COLORS[group] || GROUP_COLORS['Other'];

  return (
    <div
      style={{
        minWidth: '160px',
        padding: '12px 16px',
        backgroundColor: isExpanded ? colors.bg : '#ffffff',
        border: `2px solid ${selected ? colors.border : isExpanded ? colors.border : '#e2e8f0'}`,
        borderRadius: '10px',
        boxShadow: selected
          ? `0 4px 12px ${colors.border}40`
          : '0 2px 6px rgba(0, 0, 0, 0.06)',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        userSelect: 'none',
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: colors.border, width: '7px', height: '7px' }}
      />

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
        <span style={{
          width: '10px', height: '10px', borderRadius: '50%',
          backgroundColor: colors.dot, flexShrink: 0,
        }} />
        <span style={{
          fontSize: '13px', fontWeight: '700', color: '#1e293b',
        }}>
          {group}
        </span>
        <span style={{
          fontSize: '10px', color: '#64748b', marginLeft: 'auto',
        }}>
          {isExpanded ? '[-]' : '[+]'}
        </span>
      </div>

      <div style={{ fontSize: '10px', color: '#64748b' }}>
        {nodeCount} nodes {isExpanded ? '(click to collapse)' : '(click to expand)'}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{ background: colors.border, width: '7px', height: '7px' }}
      />
    </div>
  );
};

export default GroupHeaderNode;
