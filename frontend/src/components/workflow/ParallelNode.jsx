import { Handle, Position } from 'reactflow';

const ParallelNode = ({ data, selected }) => {
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
          background: '#06b6d4',
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
          border: `1.5px solid ${selected ? '#06b6d4' : '#22d3ee'}`,
          boxShadow: selected
            ? '0 4px 12px rgba(6, 182, 212, 0.3)'
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
              fontSize: '18px',
              color: '#06b6d4',
              fontWeight: '700',
              lineHeight: '1',
              marginBottom: '2px',
            }}
          >
            +
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '2px',
            }}
          >
            <span style={{ color: '#6b7280', fontSize: '6px', fontWeight: '600' }}>PARALLEL</span>
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Top}
        id="branch1"
        style={{
          background: '#06b6d4',
          width: '7px',
          height: '7px',
          zIndex: 10,
        }}
      />

      <Handle
        type="source"
        position={Position.Bottom}
        id="branch2"
        style={{
          background: '#0891b2',
          width: '7px',
          height: '7px',
          zIndex: 10,
        }}
      />
    </div>
  );
};

export default ParallelNode;
