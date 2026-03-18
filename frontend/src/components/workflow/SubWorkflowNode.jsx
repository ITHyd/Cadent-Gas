import { Handle, Position } from "reactflow";

const SubWorkflowNode = ({ data, selected }) => {
  const label = data.label || data.workflow_id || data.use_case || "Configure sub-workflow";
  const target = data.workflow_id || data.workflow_id_template || data.use_case || "";
  const canOpen = typeof data.onOpenSubWorkflow === "function" && !data.workflow_id_template;

  return (
    <div
      style={{
        padding: "8px 10px",
        borderRadius: "6px",
        border: `1.5px solid ${selected ? "#0f766e" : "#14b8a6"}`,
        backgroundColor: data.nodeColor || "white",
        minWidth: "130px",
        maxWidth: "170px",
        boxShadow: selected
          ? "0 4px 12px rgba(20, 184, 166, 0.28)"
          : "0 2px 8px rgba(0, 0, 0, 0.1)",
        transition: "all 0.2s ease",
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: "#14b8a6",
          width: "7px",
          height: "7px",
        }}
      />

      <div
        style={{
          fontSize: "11px",
          color: "#374151",
          lineHeight: "1.3",
          marginBottom: "4px",
          overflow: "hidden",
          textOverflow: "ellipsis",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          wordBreak: "break-word",
        }}
      >
        {label}
      </div>

      {target && (
        <div
          style={{
            fontSize: "8px",
            color: "#9ca3af",
            fontFamily: "monospace",
            marginBottom: "3px",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          target: {target}
        </div>
      )}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "6px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "4px",
          }}
        >
          <span style={{ fontSize: "10px" }}>↪</span>
          <span style={{ color: "#6b7280", fontSize: "8px", fontWeight: "600" }}>
            SUB WORKFLOW
          </span>
        </div>
        {canOpen && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              data.onOpenSubWorkflow();
            }}
            style={{
              border: "none",
              background: "#ccfbf1",
              color: "#115e59",
              borderRadius: "999px",
              padding: "3px 7px",
              fontSize: "8px",
              fontWeight: "700",
              cursor: "pointer",
            }}
            title="Open linked workflow"
          >
            Open
          </button>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: "#14b8a6",
          width: "7px",
          height: "7px",
        }}
      />
    </div>
  );
};

export default SubWorkflowNode;
