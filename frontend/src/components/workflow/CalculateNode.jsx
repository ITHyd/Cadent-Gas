import { Handle, Position } from 'reactflow';

const parseScoreWorkflow = (calc) => {
  if (!calc) return null;
  const lines = calc
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 2) return null;

  const rawMatch = lines[0].match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=/);
  const normMatch = lines[1].match(
    /^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*round\(\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\/\s*(\d+)\s*\),\s*3\)\s*if\s*\d+\s*else\s*0$/
  );
  if (!rawMatch || !normMatch) return null;
  if (rawMatch[1] !== normMatch[2]) return null;

  const inputs = [...lines[0].matchAll(/([A-Za-z_][A-Za-z0-9_]*_score)\b/g)].map((m) => m[1]);
  return {
    rawVariable: rawMatch[1],
    normalizedVariable: normMatch[1],
    maxScore: Number(normMatch[3]),
    inputCount: inputs.length,
  };
};

const CalculateNode = ({ data, selected }) => {
  const scoreWorkflow = parseScoreWorkflow(data.calculation);
  const primaryText = scoreWorkflow
    ? `Normalize ${scoreWorkflow.rawVariable}`
    : (data.calculation || 'Click to edit');
  const secondaryText = scoreWorkflow
    ? `${scoreWorkflow.inputCount} inputs • max ${scoreWorkflow.maxScore}`
    : (data.result_variable ? `result: ${data.result_variable}` : '');

  return (
    <div
      style={{
        padding: '8px 10px',
        borderRadius: '6px',
        border: `1.5px solid ${selected ? '#8b5cf6' : '#a78bfa'}`,
        backgroundColor: data.nodeColor || 'white',
        minWidth: '120px',
        maxWidth: '160px',
        boxShadow: selected
          ? '0 4px 12px rgba(139, 92, 246, 0.3)'
          : '0 2px 8px rgba(0, 0, 0, 0.1)',
        transition: 'all 0.2s ease',
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: '#8b5cf6',
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
        {primaryText}
      </div>

      {secondaryText && (
        <div
          style={{
            fontSize: '8px',
            color: '#9ca3af',
            fontFamily: scoreWorkflow ? 'inherit' : 'monospace',
            marginBottom: '3px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {secondaryText}
        </div>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
        }}
      >
        <span style={{ fontSize: '10px' }}>Σ</span>
        <span style={{ color: '#6b7280', fontSize: '8px', fontWeight: '600' }}>CALCULATE</span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: '#8b5cf6',
          width: '7px',
          height: '7px',
        }}
      />
    </div>
  );
};

export default CalculateNode;
