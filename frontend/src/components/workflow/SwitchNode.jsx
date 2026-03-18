import { Handle, Position } from 'reactflow';

const SwitchNode = ({ data, selected }) => {
  const cases = data.cases || [];
  const label = data.label || data.variable || 'Switch';

  return (
    <div
      style={{
        position: 'relative',
        minWidth: '140px',
        padding: '10px 14px',
        backgroundColor: selected ? '#f5f3ff' : '#faf5ff',
        border: `2px solid ${selected ? '#7c3aed' : '#c4b5fd'}`,
        borderRadius: '8px',
        boxShadow: selected
          ? '0 4px 12px rgba(124, 58, 237, 0.25)'
          : '0 2px 6px rgba(0, 0, 0, 0.08)',
        transition: 'all 0.2s ease',
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: '#7c3aed', width: '7px', height: '7px' }}
      />

      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
        <span style={{ fontSize: '14px' }}>&#x2443;</span>
        <span style={{ fontSize: '10px', fontWeight: '700', color: '#5b21b6', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          SWITCH
        </span>
      </div>

      <div style={{ fontSize: '11px', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
        {label}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
        {cases.map((c, i) => (
          <div key={c} style={{
            display: 'flex', alignItems: 'center', gap: '4px',
            fontSize: '9px', color: '#6b7280',
          }}>
            <span style={{
              width: '6px', height: '6px', borderRadius: '50%',
              backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'][i % 6],
              flexShrink: 0,
            }} />
            {c}
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '9px', color: '#9ca3af' }}>
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#d1d5db', flexShrink: 0 }} />
          default
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{ background: '#7c3aed', width: '7px', height: '7px' }}
      />
    </div>
  );
};

export default SwitchNode;
