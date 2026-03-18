import { Handle, Position } from 'reactflow';

const ScriptNode = ({ data, selected }) => {
  return (
    <div
      style={{
        padding: '8px 10px',
        borderRadius: '6px',
        border: `1.5px solid ${selected ? '#4338ca' : '#4f46e5'}`,
        backgroundColor: data.nodeColor || 'white',
        minWidth: '120px',
        maxWidth: '160px',
        boxShadow: selected
          ? '0 4px 12px rgba(79, 70, 229, 0.3)'
          : '0 2px 8px rgba(0, 0, 0, 0.1)',
        transition: 'all 0.2s ease',
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: '#4f46e5',
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
          fontFamily: 'monospace',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          wordBreak: 'break-word',
        }}
      >
        {data.script_code ? data.script_code.substring(0, 40) : 'Click to edit'}
      </div>

      {data.script_language && (
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
          lang: {data.script_language}
        </div>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
        }}
      >
        <span style={{ fontSize: '10px', fontFamily: 'monospace', fontWeight: '700' }}>&lt;/&gt;</span>
        <span style={{ color: '#6b7280', fontSize: '8px', fontWeight: '600' }}>SCRIPT</span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: '#4f46e5',
          width: '7px',
          height: '7px',
        }}
      />
    </div>
  );
};

export default ScriptNode;
