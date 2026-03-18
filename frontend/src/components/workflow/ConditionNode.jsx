import { Handle, Position } from 'reactflow';

const ConditionNode = ({ data, selected }) => {
  return (
    <div
      style={{
        position: 'relative',
        width: '96px',
        height: '96px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: '#f59e0b',
          width: '7px',
          height: '7px',
          zIndex: 10,
        }}
      />

      <div
        style={{
          width: '70px',
          height: '70px',
          transform: 'rotate(45deg)',
          backgroundColor: data.nodeColor || 'white',
          border: `1.5px solid ${selected ? '#f59e0b' : '#fbbf24'}`,
          boxShadow: selected
            ? '0 4px 12px rgba(245, 158, 11, 0.3)'
            : '0 2px 8px rgba(0, 0, 0, 0.1)',
          transition: 'all 0.2s ease',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            transform: 'rotate(-45deg)',
            textAlign: 'center',
            padding: '3px',
            maxWidth: '62px',
          }}
        >
          <div
            style={{
              fontSize: '9px',
              color: '#374151',
              lineHeight: '1.3',
              fontFamily: 'monospace',
              wordBreak: 'break-word',
              marginBottom: '2px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
            }}
          >
            {data.expression || 'Click to edit'}
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '2px',
            }}
          >
            <span style={{ fontSize: '7px' }}>◇</span>
            <span style={{ color: '#6b7280', fontSize: '6px', fontWeight: '600' }}>CONDITION</span>
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Top}
        id="true"
        style={{
          background: '#10b981',
          width: '7px',
          height: '7px',
          zIndex: 10,
        }}
      />

      <Handle
        type="source"
        position={Position.Bottom}
        id="false"
        style={{
          background: '#ef4444',
          width: '7px',
          height: '7px',
          zIndex: 10,
        }}
      />
    </div>
  );
};

export default ConditionNode;
