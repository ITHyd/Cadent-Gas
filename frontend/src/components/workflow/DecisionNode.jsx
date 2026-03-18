import { Handle, Position } from 'reactflow';

const DecisionNode = ({ data, selected }) => {
  const getOutcomeColor = (outcome) => {
    switch (outcome) {
      case 'emergency_dispatch':
        return '#ef4444';
      case 'schedule_engineer':
        return '#f59e0b';
      case 'monitor':
        return '#3b82f6';
      case 'close_with_guidance':
        return '#10b981';
      default:
        return '#6b7280';
    }
  };

  const getOutcomeIcon = (outcome) => {
    switch (outcome) {
      case 'emergency_dispatch':
        return '🚨';
      case 'schedule_engineer':
        return '📅';
      case 'monitor':
        return '👁️';
      case 'close_with_guidance':
        return '✅';
      default:
        return '■';
    }
  };

  const outcomeColor = getOutcomeColor(data.outcome);
  const outcomeIcon = getOutcomeIcon(data.outcome);

  return (
    <div
      style={{
        padding: '8px 10px',
        borderRadius: '6px',
        border: `1.5px solid ${outcomeColor}`,
        backgroundColor: data.nodeColor || 'white',
        minWidth: '120px',
        maxWidth: '160px',
        boxShadow: selected
          ? `0 4px 12px ${outcomeColor}40`
          : '0 2px 8px rgba(0, 0, 0, 0.1)',
        transition: 'all 0.2s ease',
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: outcomeColor,
          width: '7px',
          height: '7px',
        }}
      />

      <div
        style={{
          fontSize: '11px',
          color: outcomeColor,
          fontWeight: '600',
          marginBottom: '4px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          wordBreak: 'break-word',
        }}
      >
        {data.outcome || 'No outcome set'}
      </div>

      {data.outcome && (
        <div
          style={{
            fontSize: '8px',
            color: '#6b7280',
            marginBottom: '3px',
          }}
        >
          Workflow ends here
        </div>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
        }}
      >
        <span style={{ fontSize: '10px' }}>{outcomeIcon}</span>
        <span style={{ color: '#6b7280', fontSize: '8px', fontWeight: '600' }}>DECISION</span>
      </div>
    </div>
  );
};

export default DecisionNode;
