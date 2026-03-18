import { Handle, Position } from "reactflow";

const IntakeNode = ({ data }) => {
  const title = data?.title || "Intake Step";
  const description = data?.description || "";
  const accent = data?.accent || "#8DE971";
  const icon = data?.icon || "•";

  return (
    <div
      style={{
        minWidth: "210px",
        maxWidth: "240px",
        padding: "12px 14px",
        borderRadius: "12px",
        border: `1.5px dashed ${accent}`,
        backgroundColor: "#f8fff3",
        boxShadow: "0 4px 12px rgba(0, 0, 0, 0.06)",
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: accent, width: "8px", height: "8px" }}
      />

      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
        <span
          style={{
            width: "24px",
            height: "24px",
            borderRadius: "999px",
            backgroundColor: accent,
            color: "#173018",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "13px",
            fontWeight: 700,
            flexShrink: 0,
          }}
        >
          {icon}
        </span>
        <div style={{ fontSize: "13px", fontWeight: 700, color: "#1f2937" }}>{title}</div>
      </div>

      <div style={{ fontSize: "11px", lineHeight: 1.4, color: "#4b5563" }}>
        {description}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{ background: accent, width: "8px", height: "8px" }}
      />
    </div>
  );
};

export default IntakeNode;
