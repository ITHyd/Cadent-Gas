import { Handle, Position } from 'reactflow';

const EscalationNode = ({ data, selected }) => {
  return (
    <div
      style={{
        padding: '8px 10px',
        borderRadius: '6px',
        border: `1.5px solid ${selected ? '#92400e' : '#b45309'}`,
        backgroundColor: data.nodeColor || 'white',
        minWidth: '120px',
        maxWidth: '160px',
        boxShadow: selected
          ? '0 4px 12px rgba(180, 83, 9, 0.3)'
          : '0 2px 8px rgba(0, 0, 0, 0.1)',
        transition: 'all 0.2s ease',
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: '#b45309',
          width: '7px',
          height: '7px',
        }}
      />

      <div
        style={{
          fontSize: '11px',
          color: '#374151',
          lineHeight: '1.3',
          marginBottom: '4px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          wordBreak: 'break-word',
        }}
      >
        {data.escalation_reason || 'Click to edit'}
      </div>

      {data.escalation_level && (
        <div
          style={{
            fontSize: '8px',
            color: '#9ca3af',
            fontFamily: 'monospace',
            marginBottom: '3px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          level: {data.escalation_level}
        </div>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
        }}
      >
        <span style={{ fontSize: '10px' }}>⬆</span>
        <span style={{ color: '#6b7280', fontSize: '8px', fontWeight: '600' }}>ESCALATION</span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: '#b45309',
          width: '7px',
          height: '7px',
        }}
      />
    </div>
  );
};

export default EscalationNode;
