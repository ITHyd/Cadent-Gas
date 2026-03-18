import { Handle, Position } from 'reactflow';

const HumanOverrideNode = ({ data, selected }) => {
  return (
    <div
      style={{
        padding: '8px 10px',
        borderRadius: '6px',
        border: `1.5px solid ${selected ? '#db2777' : '#ec4899'}`,
        backgroundColor: data.nodeColor || 'white',
        minWidth: '120px',
        maxWidth: '160px',
        boxShadow: selected
          ? '0 4px 12px rgba(236, 72, 153, 0.3)'
          : '0 2px 8px rgba(0, 0, 0, 0.1)',
        transition: 'all 0.2s ease',
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: '#ec4899',
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
        {data.override_instruction || 'Click to edit'}
      </div>

      {data.assigned_role && (
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
          role: {data.assigned_role}
        </div>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
        }}
      >
        <span style={{ fontSize: '10px' }}>👤</span>
        <span style={{ color: '#6b7280', fontSize: '8px', fontWeight: '600' }}>HUMAN OVERRIDE</span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: '#ec4899',
          width: '7px',
          height: '7px',
        }}
      />
    </div>
  );
};

export default HumanOverrideNode;
