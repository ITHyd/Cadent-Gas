import { useCallback, useEffect, useState, useRef, Fragment, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import ReactFlow, {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  MiniMap,
  addEdge,
  getSmoothStepPath,
  useNodesState,
  useEdgesState,
  MarkerType,
  ConnectionLineType,
} from "reactflow";
import "reactflow/dist/style.css";

import QuestionNode from "./workflow/QuestionNode";
import ConditionNode from "./workflow/ConditionNode";
import SwitchNode from "./workflow/SwitchNode";
import GroupHeaderNode from "./workflow/GroupHeaderNode";
import DecisionNode from "./workflow/DecisionNode";
import CalculateNode from "./workflow/CalculateNode";
import MLModelNode from "./workflow/MLModelNode";
import WaitNode from "./workflow/WaitNode";
import ParallelNode from "./workflow/ParallelNode";
import HumanOverrideNode from "./workflow/HumanOverrideNode";
import TimerNode from "./workflow/TimerNode";
import NotificationNode from "./workflow/NotificationNode";
import AlertNode from "./workflow/AlertNode";
import EscalationNode from "./workflow/EscalationNode";
import ScriptNode from "./workflow/ScriptNode";
import DataFetchNode from "./workflow/DataFetchNode";
import SubWorkflowNode from "./workflow/SubWorkflowNode";
import IntakeNode from "./workflow/IntakeNode";
import NodePropertiesForm from "./workflow/NodePropertiesForm";

import {
  createWorkflow,
  updateWorkflow,
  getWorkflowVersions,
  getWorkflowVersion,
  renameWorkflowVersion,
  deleteWorkflowVersion,
  activateWorkflowVersion,
  getTenantWorkflows,
} from "../services/api";

const nodeTypes = {
  QUESTION: QuestionNode,
  CONDITION: ConditionNode,
  SWITCH: SwitchNode,
  GROUP_HEADER: GroupHeaderNode,
  DECISION: DecisionNode,
  CALCULATE: CalculateNode,
  ML_MODEL: MLModelNode,
  WAIT: WaitNode,
  PARALLEL: ParallelNode,
  HUMAN_OVERRIDE: HumanOverrideNode,
  TIMER: TimerNode,
  NOTIFICATION: NotificationNode,
  ALERT: AlertNode,
  ESCALATION: EscalationNode,
  SCRIPT: ScriptNode,
  DATA_FETCH: DataFetchNode,
  SUB_WORKFLOW: SubWorkflowNode,
  INTAKE: IntakeNode,
};

const VerticalSwitchEdge = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  label,
}) => {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const beforeTarget = 72;
  const aboveLink = 18;
  const sideNudge = 12;
  let labelX = targetX - beforeTarget;
  let labelY = targetY - aboveLink;

  if (typeof document !== "undefined") {
    try {
      const svgPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      svgPath.setAttribute("d", edgePath);
      const totalLength = svgPath.getTotalLength();
      const anchorLength = Math.max(0, totalLength - beforeTarget);
      const anchor = svgPath.getPointAtLength(anchorLength);
      const prev = svgPath.getPointAtLength(Math.max(0, anchorLength - 1));
      const tangentX = anchor.x - prev.x;
      const tangentY = anchor.y - prev.y;
      const isMostlyHorizontal = Math.abs(tangentX) >= Math.abs(tangentY);

      if (isMostlyHorizontal) {
        labelX = anchor.x;
        labelY = anchor.y - aboveLink;
      } else {
        labelX = anchor.x + sideNudge;
        labelY = anchor.y - aboveLink;
      }
    } catch (_) {
      if (targetPosition === "right") {
        labelX = targetX + beforeTarget;
        labelY = targetY - aboveLink;
      } else if (targetPosition === "top") {
        labelX = targetX + sideNudge;
        labelY = targetY - beforeTarget;
      } else if (targetPosition === "bottom") {
        labelX = targetX + sideNudge;
        labelY = targetY + beforeTarget - aboveLink;
      }
    }
  }

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />
      {label ? (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan"
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: "none",
              background: "rgba(255,255,255,0.96)",
              border: "1px solid #e5e7eb",
              borderRadius: "999px",
              padding: "2px 8px",
              color: "#374151",
              fontSize: "11px",
              lineHeight: 1.2,
              whiteSpace: "nowrap",
              maxWidth: "160px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              boxShadow: "0 1px 2px rgba(15, 23, 42, 0.08)",
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
};

const edgeTypes = {
  verticalSwitch: VerticalSwitchEdge,
};

const NODE_TYPES = [
  "QUESTION",
  "CONDITION",
  "SWITCH",
  "DECISION",
  "CALCULATE",
  "ML_MODEL",
  "WAIT",
  "PARALLEL",
  "HUMAN_OVERRIDE",
  "TIMER",
  "NOTIFICATION",
  "ALERT",
  "ESCALATION",
  "SCRIPT",
  "DATA_FETCH",
  "SUB_WORKFLOW",
];

const NODE_META = {
  QUESTION: { icon: "❓", color: "#3b82f6", label: "Question" },
  CONDITION: { icon: "◇", color: "#f59e0b", label: "Condition" },
  SWITCH: { icon: "⑃", color: "#7c3aed", label: "Switch" },
  DECISION: { icon: "■", color: "#10b981", label: "Decision" },
  CALCULATE: { icon: "Σ", color: "#8b5cf6", label: "Calculate" },
  ML_MODEL: { icon: "🤖", color: "#f97316", label: "ML Model" },
  WAIT: { icon: "⏱", color: "#64748b", label: "Wait" },
  PARALLEL: { icon: "+", color: "#06b6d4", label: "Parallel" },
  HUMAN_OVERRIDE: { icon: "👤", color: "#ec4899", label: "Human Override" },
  TIMER: { icon: "⏲", color: "#0d9488", label: "Timer" },
  NOTIFICATION: { icon: "🔔", color: "#7c3aed", label: "Notification" },
  ALERT: { icon: "⚠", color: "#dc2626", label: "Alert" },
  ESCALATION: { icon: "⬆", color: "#b45309", label: "Escalation" },
  SCRIPT: { icon: "</>", color: "#4f46e5", label: "Script" },
  DATA_FETCH: { icon: "🗄", color: "#0284c7", label: "Data Fetch" },
  SUB_WORKFLOW: { icon: "↪", color: "#14b8a6", label: "Sub-workflow" },
};

/* ── BPMN Palette SVG Icons ── */
const PALETTE_SVG = {
  DECISION: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <circle cx="14" cy="14" r="11" stroke={color} strokeWidth="3" />
      <rect x="9" y="9" width="10" height="10" rx="1" fill={color} />
    </svg>
  ),
  QUESTION: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <rect x="2" y="4" width="24" height="20" rx="3" stroke={color} strokeWidth="1.5" />
      <text x="14" y="18" textAnchor="middle" fontSize="14" fill={color} fontWeight="bold">
        ?
      </text>
    </svg>
  ),
  CALCULATE: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <rect x="2" y="4" width="24" height="20" rx="3" stroke={color} strokeWidth="1.5" />
      <text x="14" y="19" textAnchor="middle" fontSize="14" fill={color} fontWeight="bold">
        &#931;
      </text>
    </svg>
  ),
  ML_MODEL: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <rect x="2" y="4" width="24" height="20" rx="3" stroke={color} strokeWidth="1.5" />
      <circle cx="14" cy="14" r="5" stroke={color} strokeWidth="1.5" />
      <circle cx="14" cy="14" r="2" fill={color} />
    </svg>
  ),
  CONDITION: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <rect x="6" y="6" width="16" height="16" rx="1" stroke={color} strokeWidth="1.5" transform="rotate(45 14 14)" />
      <text x="14" y="18" textAnchor="middle" fontSize="12" fill={color} fontWeight="bold">
        X
      </text>
    </svg>
  ),
  PARALLEL: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <rect x="6" y="6" width="16" height="16" rx="1" stroke={color} strokeWidth="1.5" transform="rotate(45 14 14)" />
      <text x="14" y="18" textAnchor="middle" fontSize="14" fill={color} fontWeight="bold">
        +
      </text>
    </svg>
  ),
  HUMAN_OVERRIDE: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <rect x="2" y="4" width="24" height="20" rx="3" stroke={color} strokeWidth="1.5" />
      <circle cx="14" cy="10" r="3" stroke={color} strokeWidth="1.2" />
      <path d="M8 22 Q14 16 20 22" stroke={color} strokeWidth="1.2" fill="none" />
    </svg>
  ),
  WAIT: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <circle cx="14" cy="14" r="11" stroke={color} strokeWidth="1.5" />
      <circle cx="14" cy="14" r="8" stroke={color} strokeWidth="1" />
      <line x1="14" y1="14" x2="14" y2="8" stroke={color} strokeWidth="1.5" />
      <line x1="14" y1="14" x2="18" y2="14" stroke={color} strokeWidth="1.5" />
    </svg>
  ),
  NOTIFICATION: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <path
        d="M14 4C9.58 4 6 7.58 6 12v5l-2 2v1h20v-1l-2-2v-5c0-4.42-3.58-8-8-8z"
        stroke={color}
        strokeWidth="1.5"
        fill="none"
      />
      <path d="M11 22c0 1.66 1.34 3 3 3s3-1.34 3-3" stroke={color} strokeWidth="1.5" fill="none" />
    </svg>
  ),
  TIMER: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <circle cx="14" cy="15" r="10" stroke={color} strokeWidth="1.5" />
      <line x1="14" y1="15" x2="14" y2="9" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <line x1="14" y1="15" x2="19" y2="15" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <line x1="14" y1="3" x2="14" y2="5" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="11" y1="3" x2="17" y2="3" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  ALERT: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <path d="M14 4L3 24h22L14 4z" stroke={color} strokeWidth="1.5" strokeLinejoin="round" fill="none" />
      <line x1="14" y1="11" x2="14" y2="17" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <circle cx="14" cy="20" r="1" fill={color} />
    </svg>
  ),
  ESCALATION: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <rect x="2" y="4" width="24" height="20" rx="3" stroke={color} strokeWidth="1.5" />
      <path d="M14 18V8" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <path d="M9 12l5-5 5 5" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  SCRIPT: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <rect x="2" y="4" width="24" height="20" rx="3" stroke={color} strokeWidth="1.5" />
      <path d="M10 10l-3 4 3 4" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18 10l3 4-3 4" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="15" y1="9" x2="13" y2="19" stroke={color} strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  DATA_FETCH: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <ellipse cx="14" cy="8" rx="10" ry="4" stroke={color} strokeWidth="1.5" />
      <path d="M4 8v12c0 2.21 4.48 4 10 4s10-1.79 10-4V8" stroke={color} strokeWidth="1.5" />
      <ellipse cx="14" cy="14" rx="10" ry="4" stroke={color} strokeWidth="1" strokeDasharray="2 2" />
    </svg>
  ),
  SUB_WORKFLOW: (color) => (
    <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
      <rect x="2" y="4" width="18" height="20" rx="3" stroke={color} strokeWidth="1.5" />
      <path d="M12 14h11" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
      <path d="M19 10l4 4-4 4" stroke={color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};

/* ── Canvas Tool Definitions ── */
const CANVAS_TOOLS = [
  {
    id: "grab",
    label: "Hand",
    title: "Pan / Move canvas",
    svg: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 22c4.418 0 8-3.582 8-8V9a2 2 0 0 0-4 0"
          stroke="#374151"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M16 9V6a2 2 0 0 0-4 0v7"
          stroke="#374151"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M12 7V4a2 2 0 0 0-4 0v9"
          stroke="#374151"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M8 11V9a2 2 0 0 0-4 0v5c0 4.418 3.582 8 8 8"
          stroke="#374151"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  {
    id: "select",
    label: "Select",
    title: "Marquee select nodes",
    svg: (
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        stroke="#374151"
        strokeWidth="2"
        strokeLinecap="round"
      >
        <path d="M3 3h4" />
        <path d="M17 3h4" />
        <path d="M21 3v4" />
        <path d="M21 17v4" />
        <path d="M21 21h-4" />
        <path d="M7 21H3" />
        <path d="M3 21v-4" />
        <path d="M3 7V3" />
        <line x1="12" y1="8" x2="12" y2="16" />
        <line x1="8" y1="12" x2="16" y2="12" />
      </svg>
    ),
  },
  {
    id: "connect",
    label: "Connect",
    title: "Draw connections between nodes",
    svg: (
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="#374151"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M5 19L19 5" />
        <polyline points="15 5 19 5 19 9" />
        <circle cx="5" cy="19" r="2" />
      </svg>
    ),
  },
];

const PALETTE_CATEGORIES = [
  {
    label: "Events",
    items: [{ type: "DECISION", label: "End" }],
  },
  {
    label: "Tasks",
    items: [
      { type: "QUESTION", label: "Question" },
      { type: "CALCULATE", label: "Calculate" },
      { type: "ML_MODEL", label: "ML Model" },
      { type: "HUMAN_OVERRIDE", label: "Override" },
    ],
  },
  {
    label: "Gateways",
    items: [
      { type: "CONDITION", label: "Condition" },
      { type: "PARALLEL", label: "Parallel" },
    ],
  },
];

const PALETTE_MORE_CATEGORIES = [
  {
    label: "Intermediate",
    items: [
      { type: "WAIT", label: "Wait", svgKey: "WAIT" },
      { type: "TIMER", label: "Timer", svgKey: "TIMER" },
      { type: "NOTIFICATION", label: "Notification", svgKey: "NOTIFICATION" },
    ],
  },
  {
    label: "Advanced",
    items: [
      { type: "ALERT", label: "Alert", svgKey: "ALERT" },
      { type: "ESCALATION", label: "Escalation", svgKey: "ESCALATION" },
      { type: "SCRIPT", label: "Script", svgKey: "SCRIPT" },
      { type: "DATA_FETCH", label: "Data Fetch", svgKey: "DATA_FETCH" },
      { type: "SUB_WORKFLOW", label: "Sub-workflow", svgKey: "SUB_WORKFLOW" },
    ],
  },
];

const toReactFlowNodes = (backendNodes = []) =>
  backendNodes.map((node) => {
    const { position, ...restData } = node.data || {};
    return {
      id: node.id,
      type: node.type,
      position: position || { x: 0, y: 0 },
      data: { ...restData },
    };
  });

/**
 * Detect groups from node data and build a map of group → node IDs.
 */
const detectGroups = (backendNodes = []) => {
  const groups = {};
  for (const node of backendNodes) {
    const group = node.data?.group;
    if (group) {
      if (!groups[group]) groups[group] = [];
      groups[group].push(node.id);
    }
  }
  return groups;
};

/**
 * Apply collapse: for collapsed groups, hide child nodes and show a GROUP_HEADER.
 * For expanded groups, keep the GROUP_HEADER (as a label) AND show child nodes.
 * Edges are rewired so SWITCH → header, and header → first child (when expanded).
 */
const applyGroupCollapse = (flowNodes, flowEdges, groups, collapsedGroups, backendEdges = []) => {
  if (Object.keys(groups).length === 0) return { nodes: flowNodes, edges: flowEdges };

  const hiddenNodeIds = new Set();
  const headerNodes = [];
  const headerEdges = [];

  for (const [groupName, nodeIds] of Object.entries(groups)) {
    const isCollapsed = collapsedGroups.has(groupName);
    const headerId = `__group_${groupName}`;
    const firstNodeId = nodeIds[0];
    const incomingEdge = backendEdges.find((e) => e.target === firstNodeId);

    // Always create a header node for every group
    headerNodes.push({
      id: headerId,
      type: 'GROUP_HEADER',
      position: { x: 0, y: 0 },
      data: {
        groupName,
        nodeCount: nodeIds.length,
        isExpanded: !isCollapsed,
      },
    });

    // Rewire: SWITCH → header (instead of SWITCH → first child)
    if (incomingEdge) {
      headerEdges.push({
        id: `e-switch-${headerId}`,
        source: incomingEdge.source,
        target: headerId,
        label: '',
        type: 'smoothstep',
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
        markerEnd: { type: 'arrowclosed', width: 16, height: 16 },
      });
    }

    if (isCollapsed) {
      // Hide all child nodes
      nodeIds.forEach((id) => hiddenNodeIds.add(id));
    } else {
      // Expanded: add edge from header → first child node
      headerEdges.push({
        id: `e-${headerId}-${firstNodeId}`,
        source: headerId,
        target: firstNodeId,
        type: 'smoothstep',
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
        markerEnd: { type: 'arrowclosed', width: 16, height: 16 },
      });
    }
  }

  // Remove the original SWITCH → first-child edges (replaced by SWITCH → header)
  const allFirstChildIds = new Set(Object.values(groups).map((ids) => ids[0]));
  const replacedEdgeKeys = new Set();
  for (const be of backendEdges) {
    if (allFirstChildIds.has(be.target)) {
      replacedEdgeKeys.add(`${be.source}-${be.target}`);
    }
  }

  const visibleNodes = [
    ...flowNodes.filter((n) => !hiddenNodeIds.has(n.id)),
    ...headerNodes,
  ];
  const visibleEdges = [
    ...flowEdges.filter(
      (e) =>
        !hiddenNodeIds.has(e.source) &&
        !hiddenNodeIds.has(e.target) &&
        !replacedEdgeKeys.has(`${e.source.replace('e-', '')}-${e.target}`) &&
        !replacedEdgeKeys.has(`${e.source}-${e.target}`)
    ),
    ...headerEdges,
  ];

  // Remove duplicate edges (original SWITCH→child edges that we replaced)
  const edgeKeySet = new Set();
  const dedupedEdges = visibleEdges.filter((e) => {
    // Skip original edges to first child nodes (we replaced them with header edges)
    if (allFirstChildIds.has(e.target) && !e.id.startsWith('e-__group_') && !e.id.startsWith('e-switch-')) {
      const matchingHeader = headerEdges.find((he) => he.target === `__group_${
        Object.entries(groups).find(([, ids]) => ids[0] === e.target)?.[0]
      }`);
      if (matchingHeader) return false;
    }
    const key = `${e.source}→${e.target}`;
    if (edgeKeySet.has(key)) return false;
    edgeKeySet.add(key);
    return true;
  });

  return { nodes: visibleNodes, edges: dedupedEdges };
};

const needsAutoLayout = (nodes) => {
  if (nodes.length <= 1) return false;
  // Check if any node has a real saved position (not all at default 0,0)
  const hasRealPositions = nodes.some((n) => n.position && (Math.abs(n.position.x) > 1 || Math.abs(n.position.y) > 1));
  if (hasRealPositions) return false;
  return true;
};

const autoLayoutNodes = (nodes, edges, startNodeId, force = false) => {
  if (nodes.length === 0) return nodes;
  if (!force && !needsAutoLayout(nodes)) return nodes;

  // Build adjacency from edges
  const adjacency = {};
  const inDegree = {};
  nodes.forEach((n) => {
    adjacency[n.id] = [];
    inDegree[n.id] = 0;
  });
  edges.forEach((e) => {
    if (adjacency[e.source]) adjacency[e.source].push(e.target);
    if (inDegree[e.target] !== undefined) inDegree[e.target]++;
  });

  // BFS from start node to assign levels
  const levels = {};
  const visited = new Set();
  const start = startNodeId && adjacency[startNodeId] !== undefined ? startNodeId : nodes[0].id;

  const queue = [{ id: start, level: 0 }];
  visited.add(start);

  while (queue.length > 0) {
    const { id, level } = queue.shift();
    if (!levels[level]) levels[level] = [];
    levels[level].push(id);

    for (const neighbor of adjacency[id] || []) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        queue.push({ id: neighbor, level: level + 1 });
      }
    }
  }

  // Add any unvisited nodes at the end
  nodes.forEach((n) => {
    if (!visited.has(n.id)) {
      const maxLevel = Object.keys(levels).length > 0 ? Math.max(...Object.keys(levels).map(Number)) + 1 : 0;
      if (!levels[maxLevel]) levels[maxLevel] = [];
      levels[maxLevel].push(n.id);
    }
  });

  const positionMap = {};
  const nodeById = {};
  nodes.forEach((node) => {
    nodeById[node.id] = node;
  });

  // Tree-aware layout: compute subtree sizes so branches don't overlap
  const H_GAP = 250;
  const V_GAP = 100;
  const SWITCH_V_GAP = 140;
  const SWITCH_MAX_BRANCH_LEAVES = 5;
  // Cap how much vertical space a single branch can claim, so deep subtrees
  // don't push sibling branches (True/False) far apart
  const MAX_BRANCH_LEAVES = 3;

  // Build tree from BFS
  const childrenMap = {};
  const bfsVisited = new Set();
  const bfsQ = [start];
  bfsVisited.add(start);
  while (bfsQ.length > 0) {
    const curr = bfsQ.shift();
    childrenMap[curr] = [];
    for (const neighbor of adjacency[curr] || []) {
      if (!bfsVisited.has(neighbor)) {
        bfsVisited.add(neighbor);
        childrenMap[curr].push(neighbor);
        bfsQ.push(neighbor);
      }
    }
  }
  nodes.forEach((n) => {
    if (!bfsVisited.has(n.id)) childrenMap[n.id] = [];
  });

  // Compute subtree leaf count
  const subtreeSize = {};
  const computeSize = (id) => {
    const ch = childrenMap[id] || [];
    if (ch.length === 0) { subtreeSize[id] = 1; return 1; }
    let t = 0;
    for (const c of ch) t += computeSize(c);
    subtreeSize[id] = t;
    return t;
  };
  computeSize(start);

  // Assign positions: linear nodes (single child) don't consume extra vertical space
  const assignPositions = (id, level, yOffset) => {
    const currentNode = nodeById[id];
    const children = childrenMap[id] || [];
    const size = subtreeSize[id] || 1;
    const isSwitch = currentNode?.type === "SWITCH";
    const branchGap = isSwitch ? SWITCH_V_GAP : V_GAP;
    const maxBranchLeaves = isSwitch ? SWITCH_MAX_BRANCH_LEAVES : MAX_BRANCH_LEAVES;

    // Center this node within its allocated vertical band (capped)
    const clampedSelf = Math.min(size, maxBranchLeaves * Math.max(children.length, 1));
    const bandHeight = (clampedSelf - 1) * branchGap;
    positionMap[id] = {
      x: 60 + level * H_GAP,
      y: yOffset + bandHeight / 2,
    };

    if (children.length === 1) {
      // Single child: place at same Y (no vertical spread)
      assignPositions(children[0], level + 1, yOffset);
    } else {
      // Multiple children: stack them, cap each branch's claimed height so
      // True/False siblings don't end up far apart on deep workflows
      let childY = yOffset;
      for (const child of children) {
        assignPositions(child, level + 1, childY);
        const childNode = nodeById[child];
        const childIsSwitch = childNode?.type === "SWITCH";
        const childBranchGap = childIsSwitch ? SWITCH_V_GAP : branchGap;
        const childMaxBranchLeaves = childIsSwitch ? SWITCH_MAX_BRANCH_LEAVES : maxBranchLeaves;
        const clampedSize = Math.min(subtreeSize[child] || 1, childMaxBranchLeaves);
        childY += clampedSize * childBranchGap;
      }
    }
  };
  assignPositions(start, 0, 60);

  return nodes.map((node) => ({
    ...node,
    position: positionMap[node.id] || node.position,
  }));
};

const toReactFlowEdges = (backendEdges = [], backendNodes = []) => {
  const nodeTypeMap = {};
  backendNodes.forEach((n) => {
    nodeTypeMap[n.id] = n.type;
  });
  const usedHandles = {};

  return backendEdges.map((edge, index) => {
    let sh = edge.source_handle || null;
    const srcType = nodeTypeMap[edge.source];

    // Infer missing source_handle for existing workflows saved before handle fix
    if (!sh && (srcType === "CONDITION" || srcType === "PARALLEL")) {
      const handles = srcType === "CONDITION" ? ["true", "false"] : ["branch1", "branch2"];
      if (!usedHandles[edge.source]) usedHandles[edge.source] = new Set();
      sh = handles.find((h) => !usedHandles[edge.source].has(h)) || handles[0];
      usedHandles[edge.source].add(sh);
    }

    // Hide manufacturer== conditions on SWITCH edges (group headers show the name)
    const rawLabel = edge.condition || getEdgeLabelForHandle(srcType, sh);
    const isSwitchLabeledEdge = srcType === "SWITCH" && rawLabel;
    let label = (rawLabel && rawLabel.startsWith('manufacturer ==')) ? '' : rawLabel;
    if (isSwitchLabeledEdge && label) {
      const match = label.match(/==\s*['"](.+?)['"]$/);
      if (match?.[1]) {
        label = match[1];
      } else if (label.toLowerCase() === "default") {
        label = "default";
      }
    }

    return {
      id: `edge_${index}_${edge.source}_${edge.target}`,
      source: edge.source,
      target: edge.target,
      sourceHandle: sh,
      targetHandle: edge.target_handle || null,
      label,
      type: srcType === "SWITCH" && label ? "verticalSwitch" : "smoothstep",
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    };
  });
};

const COLOR_CHOICES = [
  { name: "Blue", value: "#dbeafe" },
  { name: "Green", value: "#d1fae5" },
  { name: "Amber", value: "#fef3c7" },
  { name: "Red", value: "#fee2e2" },
  { name: "Violet", value: "#ede9fe" },
  { name: "Pink", value: "#fce7f3" },
];

const findAvailablePosition = (basePosition, nodes) => {
  const COLLIDE_X = 160;
  const COLLIDE_Y = 90;

  const isOccupied = (pos) =>
    nodes.some(
      (n) => Math.abs((n.position?.x || 0) - pos.x) < COLLIDE_X && Math.abs((n.position?.y || 0) - pos.y) < COLLIDE_Y,
    );

  let pos = { ...basePosition };
  for (let i = 0; i < 12; i += 1) {
    if (!isOccupied(pos)) return pos;
    pos = { x: pos.x, y: pos.y + 140 };
  }
  return { x: basePosition.x + 240, y: basePosition.y };
};

const parseScoreWorkflowDescription = (calc) => {
  if (!calc) return null;
  const lines = calc
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 2) return null;
  const rawMatch = lines[0].match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=/);
  const normMatch = lines[1].match(
    /^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*round\(\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\/\s*(\d+)\s*\),\s*3\)\s*if\s*\d+\s*else\s*0$/
  );
  if (!rawMatch || !normMatch || rawMatch[1] !== normMatch[2]) return null;
  return `Normalize ${rawMatch[1]} to ${normMatch[1]}`;
};

const getNodeDescription = (node) => {
  const d = node.data || {};
  switch (node.type) {
    case "QUESTION":
      return d.question || "No question set";
    case "CONDITION":
      return d.expression || "No expression set";
    case "DECISION":
      return d.outcome?.replaceAll("_", " ") || "No outcome set";
    case "CALCULATE": {
      const scoreDescription = parseScoreWorkflowDescription(d.calculation);
      if (scoreDescription) return scoreDescription;
      if (d.result_variable && d._calc_operation && d._calc_terms?.length) {
        const op = d._calc_operation;
        const termNames = d._calc_terms.map(t => t.type === 'constant' ? t.value : t.value).join(
          ['min','max','average'].includes(op) ? ', ' : ` ${op === 'add' ? '+' : op === 'subtract' ? '−' : op === 'multiply' ? '×' : op === 'divide' ? '÷' : '+'} `
        );
        const wrap = ['min','max','average'].includes(op) ? `${op}(${termNames})` : termNames;
        return `${d.result_variable} = ${wrap}`;
      }
      return d.calculation || "No calculation set";
    }
    case "ML_MODEL":
      return d.model_name || "No model configured";
    case "WAIT":
      return d.wait_condition || "No wait condition set";
    case "PARALLEL":
      return `${d.merge_strategy === "any" ? "First completes" : "All complete"}`;
    case "HUMAN_OVERRIDE":
      return d.override_instruction || "No instruction set";
    case "TIMER":
      return d.timer_label || `${d.duration || 0}s timer`;
    case "NOTIFICATION":
      return d.notification_message || "No message set";
    case "ALERT":
      return d.alert_message || "No alert set";
    case "ESCALATION":
      return d.escalation_reason || "No reason set";
    case "SCRIPT":
      return d.script_code?.substring(0, 40) || "No script set";
    case "DATA_FETCH":
      return d.source_name || "No source configured";
    case "SUB_WORKFLOW":
      return d.label || d.workflow_id || d.use_case || "No sub-workflow configured";
    default:
      return "Unknown node";
  }
};

const getTopologicalOrder = (nodes, edges, startNodeId) => {
  if (nodes.length === 0) return [];

  const adjacency = {};
  nodes.forEach((n) => {
    adjacency[n.id] = [];
  });
  edges.forEach((e) => {
    if (adjacency[e.source]) adjacency[e.source].push(e.target);
  });

  const visited = new Set();
  const ordered = [];

  const bfs = (startId) => {
    const queue = [startId];
    visited.add(startId);
    while (queue.length > 0) {
      const current = queue.shift();
      const node = nodes.find((n) => n.id === current);
      if (node) ordered.push(node);
      for (const neighbor of adjacency[current] || []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push(neighbor);
        }
      }
    }
  };

  if (startNodeId && adjacency[startNodeId] !== undefined) {
    bfs(startNodeId);
  }

  nodes.forEach((n) => {
    if (!visited.has(n.id)) bfs(n.id);
  });

  return ordered;
};

/**
 * For CONDITION/PARALLEL nodes, pick the first available source handle
 * (i.e., the one that doesn't already have an outgoing edge).
 */
const getSmartSourceHandle = (srcNode, edges) => {
  if (!srcNode) return null;
  if (srcNode.type === "CONDITION") {
    const trueUsed = edges.some((e) => e.source === srcNode.id && e.sourceHandle === "true");
    return trueUsed ? "false" : "true";
  }
  if (srcNode.type === "PARALLEL") {
    const b1Used = edges.some((e) => e.source === srcNode.id && e.sourceHandle === "branch1");
    return b1Used ? "branch2" : "branch1";
  }
  return null;
};

const getEdgeLabelForHandle = (nodeType, handleId) => {
  if (nodeType === "CONDITION") return handleId === "true" ? "True" : "False";
  if (nodeType === "PARALLEL") return handleId === "branch1" ? "Branch 1" : "Branch 2";
  return "";
};

/**
 * Build a standard edge config with path offsets for branching nodes
 * so that edges from the same source don't overlap each other.
 */
const buildEdgeConfig = (source, target, sourceHandle, nodeType, extraProps = {}) => {
  const label = getEdgeLabelForHandle(nodeType, sourceHandle);

  return {
    source,
    target,
    sourceHandle,
    label,
    type: "smoothstep",
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    ...extraProps,
  };
};

const WorkflowBuilderVisual = ({ workflow, tenantId, onClose }) => {
  const navigate = useNavigate();
  const isEditMode = Boolean(workflow?.workflow_id);
  const reactFlowWrapper = useRef(null);
  const [reactFlowInstance, setReactFlowInstance] = useState(null);

  /** Centre viewport on the start node at a readable zoom instead of fitting all nodes */
  const zoomToStart = useCallback((instance, layoutedNodes, startId) => {
    if (!instance || layoutedNodes.length === 0) return;
    const startNode = layoutedNodes.find((n) => n.id === startId) || layoutedNodes[0];
    if (!startNode) return;
    const wrapper = reactFlowWrapper.current;
    const wH = wrapper?.offsetHeight || 600;
    const zoom = 1;
    const x = -startNode.position.x * zoom + 60;
    const y = -startNode.position.y * zoom + wH / 2 - 40;
    instance.setViewport({ x, y, zoom });
  }, []);

  const [workflowId, setWorkflowId] = useState(workflow?.workflow_id || "");
  const [useCase, setUseCase] = useState(workflow?.use_case || "");
  const [version, setVersion] = useState(workflow?.version || 1);
  const normalizedUseCase = (useCase || "").trim().toLowerCase();
  const safetyCriticalValidation =
    normalizedUseCase.startsWith("co_") ||
    ["gas_smell", "hissing_sound", "suspected_co_leak"].includes(normalizedUseCase);
  const [startNode, setStartNode] = useState(workflow?.start_node || "");

  // Detect groups and start with all manufacturer groups collapsed
  const detectedGroups = detectGroups(workflow?.nodes || []);
  const [collapsedGroups, setCollapsedGroups] = useState(
    () => new Set()
  );

  const initialFlowNodes = toReactFlowNodes(workflow?.nodes || []);
  const initialFlowEdges = toReactFlowEdges(workflow?.edges || [], workflow?.nodes || []);

  // Apply collapse before layout
  const { nodes: visibleInitNodes, edges: visibleInitEdges } = applyGroupCollapse(
    initialFlowNodes, initialFlowEdges, detectedGroups, collapsedGroups, workflow?.edges || []
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(
    autoLayoutNodes(visibleInitNodes, visibleInitEdges, workflow?.start_node || visibleInitNodes[0]?.id),
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(visibleInitEdges);

  // Toggle group collapse/expand
  const toggleGroup = useCallback((groupName) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupName)) {
        next.delete(groupName);
      } else {
        next.add(groupName);
      }
      return next;
    });
  }, []);

  // Re-apply collapse when collapsedGroups changes (no viewport jump)
  useEffect(() => {
    const groups = detectGroups(workflow?.nodes || []);
    if (Object.keys(groups).length === 0) return;

    const allFlowNodes = toReactFlowNodes(workflow?.nodes || []);
    const allFlowEdges = toReactFlowEdges(workflow?.edges || [], workflow?.nodes || []);
    const { nodes: visNodes, edges: visEdges } = applyGroupCollapse(
      allFlowNodes, allFlowEdges, groups, collapsedGroups, workflow?.edges || []
    );
    const startId = workflow?.start_node || visNodes[0]?.id || "";
    const layouted = autoLayoutNodes(visNodes, visEdges, startId, true);
    setNodes(layouted);
    setEdges(visEdges);
    // No zoomToStart here — keep viewport where user is looking
  }, [collapsedGroups]);

  const [selectedNode, setSelectedNode] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [statusFading, setStatusFading] = useState(false);
  useEffect(() => {
    if (!statusMessage) {
      setStatusFading(false);
      return;
    }
    setStatusFading(false);
    const fadeTimer = setTimeout(() => setStatusFading(true), 2500);
    const clearTimer = setTimeout(() => setStatusMessage(""), 3000);
    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(clearTimer);
    };
  }, [statusMessage]);
  const [error, setError] = useState("");
  const [rightTab, setRightTab] = useState("overview");
  const [highlightFields, setHighlightFields] = useState({});
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const dragIdxRef = useRef(null);
  const [paletteOpen, setPaletteOpen] = useState(true);
  const [paletteMoreOpen, setPaletteMoreOpen] = useState(false);
  const [activeTool, setActiveTool] = useState(null);
  const [paletteSearch, setPaletteSearch] = useState("");
  const [contextPad, setContextPad] = useState(null);
  const [contextMoreOpen, setContextMoreOpen] = useState(false);
  const [contextMoreSearch, setContextMoreSearch] = useState("");
  const [contextColorOpen, setContextColorOpen] = useState(false);
  const [previewGhost, setPreviewGhost] = useState(null);
  const hideContextPadRef = useRef(null);
  const [selectionPad, setSelectionPad] = useState(null);
  const [selectionColorOpen, setSelectionColorOpen] = useState(false);
  const [connectSource, setConnectSource] = useState(null);
  const ignorePaneClickRef = useRef(false);
  const [versions, setVersions] = useState([]);
  const [, setIsLoadingVersion] = useState(false);
  const [activeVersion, setActiveVersion] = useState(null);
  const [editingVersionLabel, setEditingVersionLabel] = useState(null);
  const [editLabelValue, setEditLabelValue] = useState("");
  const [confirmDeleteVersion, setConfirmDeleteVersion] = useState(null);
  const [tenantWorkflowRoutes, setTenantWorkflowRoutes] = useState({});

  useEffect(() => {
    const loadTenantWorkflowRoutes = async () => {
      if (!tenantId) {
        setTenantWorkflowRoutes({});
        return;
      }

      try {
        const allWorkflows = await getTenantWorkflows(tenantId);
        const latestByUseCase = new Map();
        (Array.isArray(allWorkflows) ? allWorkflows : []).forEach((item) => {
          const existing = latestByUseCase.get(item.use_case);
          if (!existing || Number(item.version) > Number(existing.version)) {
            latestByUseCase.set(item.use_case, item);
          }
        });

        const routeMap = {};
        latestByUseCase.forEach((item) => {
          if (item.workflow_id) routeMap[item.workflow_id] = item.use_case;
          if (item.use_case) routeMap[item.use_case] = item.use_case;
        });
        setTenantWorkflowRoutes(routeMap);
      } catch (_) {
        setTenantWorkflowRoutes({});
      }
    };

    loadTenantWorkflowRoutes();
  }, [tenantId]);

  const openSubWorkflow = useCallback(
    (node) => {
      const targetWorkflowId = node?.data?.workflow_id?.trim?.() || "";
      const targetUseCase = node?.data?.use_case?.trim?.() || "";
      const routeUseCase =
        tenantWorkflowRoutes[targetWorkflowId] ||
        tenantWorkflowRoutes[targetUseCase] ||
        targetUseCase;

      if (!routeUseCase) return;
      navigate(`/super/workflows/${routeUseCase}`);
    },
    [navigate, tenantWorkflowRoutes],
  );

  const interactiveNodes = useMemo(
    () =>
      nodes.map((node) =>
        node.type === "SUB_WORKFLOW"
          ? {
              ...node,
              data: {
                ...node.data,
                onOpenSubWorkflow: () => openSubWorkflow(node),
              },
            }
          : node,
      ),
    [nodes, openSubWorkflow],
  );

  const visualNodes = interactiveNodes;
  const visualEdges = edges;
  const visualStartNodeId = startNode;

  useEffect(() => {
    const backendNodes = workflow?.nodes || [];
    const backendEdges = workflow?.edges || [];
    const flowNodes = toReactFlowNodes(backendNodes);
    const flowEdges = toReactFlowEdges(backendEdges, backendNodes);

    // Detect groups and reset collapse state (expanded by default)
    const groups = detectGroups(backendNodes);
    const groupNames = Object.keys(groups);
    if (groupNames.length > 0) {
      setCollapsedGroups(new Set());
    }

    // Apply collapse before layout
    const { nodes: visNodes, edges: visEdges } = applyGroupCollapse(
      flowNodes, flowEdges, groups, new Set(), backendEdges
    );
    const startId = workflow?.start_node || visNodes[0]?.id || "";
    const layoutedNodes = autoLayoutNodes(visNodes, visEdges, startId, true);

    setWorkflowId(workflow?.workflow_id || "");
    setUseCase(workflow?.use_case || "");
    setVersion(workflow?.version || 1);
    setStartNode(startId);
    setNodes(layoutedNodes);
    setEdges(visEdges);
    setSelectedNode(null);
    setStatusMessage("");
    setError("");
    if (reactFlowInstance && layoutedNodes.length > 0) {
      setTimeout(() => zoomToStart(reactFlowInstance, layoutedNodes, startId), 100);
    }
  }, [workflow, setNodes, setEdges, reactFlowInstance, zoomToStart]);

  useEffect(() => {
    const loadVersions = async () => {
      if (!workflow?.workflow_id) {
        setVersions([]);
        setActiveVersion(null);
        return;
      }
      try {
        const data = await getWorkflowVersions(workflow.workflow_id);
        const list = Array.isArray(data?.versions) ? data.versions : [];
        setVersions(list);
        const actVer = data?.active_version ?? null;
        setActiveVersion(actVer);
        // If the loaded version differs from the active version, load the active one
        if (actVer != null && actVer !== (workflow?.version || 1)) {
          try {
            const activeData = await getWorkflowVersion(workflow.workflow_id, actVer);
            const bNodes = activeData?.nodes || [];
            const bEdges = activeData?.edges || [];
            const flowNodes = toReactFlowNodes(bNodes);
            const flowEdges = toReactFlowEdges(bEdges, bNodes);
            const groups = detectGroups(bNodes);
            const groupNames = Object.keys(groups);
            if (groupNames.length > 0) setCollapsedGroups(new Set());
            const { nodes: visN, edges: visE } = applyGroupCollapse(
              flowNodes, flowEdges, groups, new Set(), bEdges
            );
            const startId = activeData?.start_node || visN[0]?.id || "";
            const layoutedNodes = autoLayoutNodes(visN, visE, startId, true);
            setWorkflowId(activeData?.workflow_id || workflow.workflow_id);
            setUseCase(activeData?.use_case || useCase);
            setVersion(activeData?.version || actVer);
            setStartNode(startId);
            setNodes(layoutedNodes);
            setEdges(visE);
            setSelectedNode(null);
            if (reactFlowInstance && layoutedNodes.length > 0) {
              setTimeout(() => zoomToStart(reactFlowInstance, layoutedNodes, startId), 100);
            }
          } catch (_) {
            /* keep the version loaded from prop */
          }
        }
      } catch (err) {
        setVersions([]);
      }
    };
    loadVersions();
  }, [workflow?.workflow_id]);

  const onConnect = useCallback(
    (params) => {
      const srcNode = nodes.find((n) => n.id === params.source);
      const edgeConfig = buildEdgeConfig(params.source, params.target, params.sourceHandle, srcNode?.type, {
        targetHandle: params.targetHandle,
      });
      setEdges((eds) => addEdge(edgeConfig, eds));
    },
    [nodes, setEdges],
  );

  const updateContextPadPosition = useCallback((nodeId) => {
    const el = document.querySelector(`[data-id="${nodeId}"]`);
    if (el && reactFlowWrapper.current) {
      const rect = el.getBoundingClientRect();
      const canvasRect = reactFlowWrapper.current.getBoundingClientRect();
      setContextPad({
        nodeId,
        x: rect.left - canvasRect.left + rect.width / 2,
        y: rect.bottom - canvasRect.top + 8,
      });
    }
  }, []);

  useEffect(() => {
    if (!contextPad || activeTool === "select") return;

    const rafId = requestAnimationFrame(() => {
      updateContextPadPosition(contextPad.nodeId);
    });

    return () => cancelAnimationFrame(rafId);
  }, [nodes, contextPad, activeTool, updateContextPadPosition]);

  const onNodeClick = useCallback(
    (event, node) => {
      // Handle group header click → toggle collapse/expand
      if (node.type === "GROUP_HEADER" && node.data?.groupName) {
        toggleGroup(node.data.groupName);
        return;
      }
      if (activeTool === "connect") {
        if (!connectSource) {
          setConnectSource(node.id);
          return;
        }
        if (connectSource !== node.id) {
          const srcNode = nodes.find((n) => n.id === connectSource);
          const srcHandle = getSmartSourceHandle(srcNode, edges);
          const edgeConfig = buildEdgeConfig(connectSource, node.id, srcHandle, srcNode?.type);
          setEdges((eds) => addEdge(edgeConfig, eds));
        }
        setConnectSource(null);
        setActiveTool(null);
        return;
      }
      setSelectedNode(node);
      setRightTab("edit");
    },
    [activeTool, connectSource, nodes, edges, setEdges, toggleGroup],
  );

  const onNodeMouseEnter = useCallback(
    (event, node) => {
      if (activeTool === "select") return;
      if (hideContextPadRef.current) {
        clearTimeout(hideContextPadRef.current);
        hideContextPadRef.current = null;
      }
      setContextMoreOpen(false);
      setContextColorOpen(false);
      setTimeout(() => updateContextPadPosition(node.id), 0);
    },
    [updateContextPadPosition, activeTool],
  );

  const onNodeMouseLeave = useCallback(() => {
    if (activeTool === "select") return;
    hideContextPadRef.current = setTimeout(() => {
      setContextPad(null);
      setContextMoreOpen(false);
      setContextColorOpen(false);
      setPreviewGhost(null);
    }, 300);
  }, [activeTool]);

  const handleNodeColorChange = useCallback(
    (nodeIdOrIds, color) => {
      const ids = Array.isArray(nodeIdOrIds) ? nodeIdOrIds : [nodeIdOrIds];
      setNodes((nds) =>
        nds.map((node) => (ids.includes(node.id) ? { ...node, data: { ...node.data, nodeColor: color } } : node)),
      );
    },
    [setNodes],
  );

  const onPaneClick = useCallback(() => {
    if (ignorePaneClickRef.current) return;
    setSelectedNode(null);
    setContextPad(null);
    setContextMoreOpen(false);
    setContextColorOpen(false);
    setSelectionPad(null);
    setSelectionColorOpen(false);
    if (activeTool === "connect") {
      setConnectSource(null);
    }
  }, [activeTool]);

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event) => {
      event.preventDefault();
      const type = event.dataTransfer.getData("application/reactflow");
      if (!type || !reactFlowInstance) return;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const presetStr = event.dataTransfer.getData("application/preset");
      const presetData = presetStr ? JSON.parse(presetStr) : {};

      const nodeId = `${type.toLowerCase()}_${Date.now()}`;
      const nextPosition = findAvailablePosition(position, nodes);
      const newNode = {
        id: nodeId,
        type,
        position: nextPosition,
        data: { ...presetData },
      };

      setNodes((nds) => nds.concat(newNode));
      setSelectedNode(newNode);
      setRightTab("edit");

      if (!startNode) setStartNode(nodeId);
    },
    [reactFlowInstance, setNodes, startNode],
  );

  const handleAddNode = useCallback(
    (type, presetData = {}) => {
      const nodeId = `${type.toLowerCase()}_${Date.now()}`;

      // Connect to the currently selected node (last clicked), not the last in array
      const anchorNode = selectedNode ? nodes.find((n) => n.id === selectedNode.id) : null;
      let position;
      if (anchorNode) {
        position = { x: anchorNode.position.x + 240, y: anchorNode.position.y };
      } else if (reactFlowInstance) {
        const { x, y, zoom } = reactFlowInstance.getViewport();
        position = { x: (-x + 300) / zoom, y: (-y + 60) / zoom };
      } else {
        position = { x: 100, y: 50 };
      }

      const nextPosition = findAvailablePosition(position, nodes);
      const newNode = {
        id: nodeId,
        type,
        position: nextPosition,
        data: { ...presetData },
      };
      setNodes((nds) => nds.concat(newNode));

      // Auto-connect to the selected node
      if (anchorNode) {
        const srcHandle = getSmartSourceHandle(anchorNode, edges);
        const edgeConfig = buildEdgeConfig(anchorNode.id, nodeId, srcHandle, anchorNode.type);
        setEdges((eds) => addEdge(edgeConfig, eds));
      }

      setSelectedNode(newNode);
      setRightTab("edit");
      if (!startNode) setStartNode(nodeId);
    },
    [nodes, edges, selectedNode, setNodes, setEdges, startNode, reactFlowInstance],
  );

  const handleNodeDataChange = useCallback(
    (updatedData) => {
      if (!selectedNode) return;
      setNodes((nds) =>
        nds.map((node) => (node.id === selectedNode.id ? { ...node, data: { ...node.data, ...updatedData } } : node)),
      );
      setSelectedNode((prev) => (prev ? { ...prev, data: { ...prev.data, ...updatedData } } : null));
    },
    [selectedNode, setNodes],
  );

  const handleDeleteNode = useCallback(
    (nodeId) => {
      setNodes((nds) => nds.filter((node) => node.id !== nodeId));
      setEdges((eds) => eds.filter((edge) => edge.source !== nodeId && edge.target !== nodeId));
      if (startNode === nodeId) {
        const remaining = nodes.filter((node) => node.id !== nodeId);
        setStartNode(remaining[0]?.id || "");
      }
      if (selectedNode?.id === nodeId) {
        setSelectedNode(null);
        setContextPad(null);
        setRightTab("overview");
      }
    },
    [nodes, startNode, selectedNode, setNodes, setEdges],
  );

  const handleDeleteSelectedNodes = useCallback(
    (nodeIds) => {
      const idSet = new Set(nodeIds);
      setNodes((nds) => nds.filter((node) => !idSet.has(node.id)));
      setEdges((eds) => eds.filter((edge) => !idSet.has(edge.source) && !idSet.has(edge.target)));
      if (idSet.has(startNode)) {
        const remaining = nodes.filter((node) => !idSet.has(node.id));
        setStartNode(remaining[0]?.id || "");
      }
      setSelectedNode(null);
      setSelectionPad(null);
      setSelectionColorOpen(false);
      setRightTab("overview");
    },
    [nodes, startNode, setNodes, setEdges],
  );

  const onNodesDelete = useCallback(
    (deletedNodes) => {
      const idSet = new Set(deletedNodes.map((n) => n.id));
      setEdges((eds) => eds.filter((edge) => !idSet.has(edge.source) && !idSet.has(edge.target)));
      if (idSet.has(startNode)) {
        const remaining = nodes.filter((node) => !idSet.has(node.id));
        setStartNode(remaining[0]?.id || "");
      }
      if (selectedNode && idSet.has(selectedNode.id)) {
        setSelectedNode(null);
        setContextPad(null);
        setRightTab("overview");
      }
      setSelectionPad(null);
      setSelectionColorOpen(false);
    },
    [nodes, startNode, selectedNode, setEdges],
  );

  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes }) => {
      if (selectedNodes.length === 1) {
        setSelectedNode(selectedNodes[0]);
        setRightTab("edit");
        setSelectionPad(null);
        setSelectionColorOpen(false);
        return;
      }
      if (selectedNodes.length > 1 && reactFlowWrapper.current) {
        const canvasRect = reactFlowWrapper.current.getBoundingClientRect();
        let maxRight = -Infinity;
        let minTop = Infinity;
        const ids = selectedNodes.map((n) => n.id);

        selectedNodes.forEach((n) => {
          const el = document.querySelector(`[data-id="${n.id}"]`);
          if (el) {
            const rect = el.getBoundingClientRect();
            if (rect.right > maxRight) maxRight = rect.right;
            if (rect.top < minTop) minTop = rect.top;
          }
        });

        if (maxRight > -Infinity) {
          setSelectionPad({
            nodeIds: ids,
            x: maxRight - canvasRect.left + 12,
            y: minTop - canvasRect.top - 8,
          });
        }
      } else {
        setSelectionPad(null);
        setSelectionColorOpen(false);
      }
    },
    [setSelectedNode, setRightTab],
  );

  const handleQuickAdd = useCallback(
    (fromNodeId, newType) => {
      const fromNode = nodes.find((n) => n.id === fromNodeId);
      if (!fromNode) return;
      const nodeId = `${newType.toLowerCase()}_${Date.now()}`;
      const position = { x: fromNode.position.x + 240, y: fromNode.position.y };
      const nextPosition = findAvailablePosition(position, nodes);
      const newNode = {
        id: nodeId,
        type: newType,
        position: nextPosition,
        data: {},
      };
      setNodes((nds) => nds.concat(newNode));
      const srcHandle = getSmartSourceHandle(fromNode, edges);
      const edgeConfig = buildEdgeConfig(fromNodeId, nodeId, srcHandle, fromNode.type);
      setEdges((eds) => addEdge(edgeConfig, eds));
      setSelectedNode(newNode);
      setRightTab("edit");
      setContextPad(null);
      setPreviewGhost(null);
    },
    [nodes, edges, setNodes, setEdges],
  );

  const showPreviewGhost = useCallback(
    (fromNodeId, newType) => {
      const fromNode = nodes.find((n) => n.id === fromNodeId);
      if (!fromNode) return;
      const position = { x: fromNode.position.x + 240, y: fromNode.position.y };
      const nextPosition = findAvailablePosition(position, nodes);
      /* Read actual rendered size from DOM */
      const el = document.querySelector(`[data-id="${fromNodeId}"]`);
      const srcW = el ? el.offsetWidth : fromNode.type === "CONDITION" || fromNode.type === "PARALLEL" ? 96 : 140;
      const srcH = el ? el.offsetHeight : fromNode.type === "CONDITION" || fromNode.type === "PARALLEL" ? 96 : 44;
      /* Determine which handle would be used */
      const srcHandle = getSmartSourceHandle(fromNode, edges);
      setPreviewGhost({
        type: newType,
        position: nextPosition,
        sourcePos: fromNode.position,
        sourceType: fromNode.type,
        sourceW: srcW,
        sourceH: srcH,
        sourceHandle: srcHandle,
      });
    },
    [nodes, edges],
  );

  const handleOverviewReorder = useCallback(
    (fromIdx, toIdx) => {
      if (fromIdx === toIdx) return;
      const sorted = getTopologicalOrder(nodes, edges, startNode);
      const reordered = [...sorted];
      const [moved] = reordered.splice(fromIdx, 1);
      reordered.splice(toIdx, 0, moved);

      const newEdges = [];
      for (let i = 0; i < reordered.length - 1; i++) {
        const src = reordered[i];
        const tgt = reordered[i + 1];
        const srcHandle = src.type === "CONDITION" ? "true" : src.type === "PARALLEL" ? "branch1" : null;
        const edgeConfig = buildEdgeConfig(src.id, tgt.id, srcHandle, src.type, {
          id: `edge_${i}_${src.id}_${tgt.id}`,
          targetHandle: null,
        });
        newEdges.push(edgeConfig);
      }

      setEdges(newEdges);
      setStartNode(reordered[0].id);
    },
    [nodes, edges, startNode, setEdges],
  );

  const handleSaveWorkflow = async () => {
    setError("");
    setStatusMessage("");
    setHighlightFields({});

    if (!workflowId.trim() || !useCase.trim()) {
      const fields = {};
      if (!workflowId.trim()) fields.workflowId = true;
      if (!useCase.trim()) fields.useCase = true;
      setHighlightFields(fields);
      setError(
        !workflowId.trim() && !useCase.trim()
          ? "Please enter Workflow ID and Use Case before saving."
          : !workflowId.trim()
            ? "Please enter a Workflow ID before saving."
            : "Please enter a Use Case before saving.",
      );
      return;
    }
    if (nodes.length === 0) {
      setError("Add at least one node before saving.");
      return;
    }

    const payload = {
      workflow_id: workflowId.trim(),
      tenant_id: tenantId,
      use_case: useCase.trim(),
      start_node: startNode || nodes[0].id,
      nodes: nodes.map((node) => ({
        id: node.id,
        type: node.type,
        data: { ...node.data, position: node.position },
      })),
      edges: edges.map((edge) => ({
        source: edge.source,
        target: edge.target,
        source_handle: edge.sourceHandle,
        target_handle: edge.targetHandle,
        condition: edge.label?.trim() ? edge.label.trim() : null,
      })),
    };

    setIsSaving(true);
    try {
      let saved;
      if (isEditMode) {
        saved = await updateWorkflow(workflow.workflow_id, payload);
      } else {
        saved = await createWorkflow({ ...payload, version: 1 });
      }
      setVersion(saved.version);
      setActiveVersion(saved.version);
      setStatusMessage(`Workflow saved! Version ${saved.version} is now active.`);
      // Refresh versions list after save
      const wfId = saved.workflow_id || workflow?.workflow_id;
      if (wfId) {
        try {
          const data = await getWorkflowVersions(wfId);
          setVersions(Array.isArray(data?.versions) ? data.versions : []);
          setActiveVersion(data?.active_version ?? saved.version);
        } catch (_) {
          /* ignore */
        }
      }
    } catch (saveError) {
      setError(saveError.message || "Failed to save workflow");
    } finally {
      setIsSaving(false);
    }
  };

  const loadVersion = async (nextVersion) => {
    const normalized = Number(nextVersion);
    if (!workflow?.workflow_id || Number.isNaN(normalized)) return;
    if (normalized === version) return;
    setIsLoadingVersion(true);
    setError("");
    try {
      const data = await getWorkflowVersion(workflow.workflow_id, normalized);
      const flowNodes = toReactFlowNodes(data?.nodes || []);
      const flowEdges = toReactFlowEdges(data?.edges || [], data?.nodes || []);
      const startId = data?.start_node || flowNodes[0]?.id || "";
      const layoutedNodes = autoLayoutNodes(flowNodes, flowEdges, startId);
      setWorkflowId(data?.workflow_id || workflow.workflow_id);
      setUseCase(data?.use_case || useCase);
      setVersion(data?.version || normalized);
      setStartNode(startId);
      setNodes(layoutedNodes);
      setEdges(flowEdges);
      setSelectedNode(null);
      setRightTab("versions");
      setStatusMessage("");
      if (reactFlowInstance && layoutedNodes.length > 0) {
        setTimeout(() => zoomToStart(reactFlowInstance, layoutedNodes, startId), 100);
      }
    } catch (err) {
      setError(err.message || "Failed to load workflow version");
    } finally {
      setIsLoadingVersion(false);
    }
  };

  const handleRenameVersion = async (versionNum, newLabel) => {
    if (!newLabel || !newLabel.trim() || !workflow?.workflow_id) return;
    try {
      await renameWorkflowVersion(workflow.workflow_id, versionNum, newLabel.trim());
      const data = await getWorkflowVersions(workflow.workflow_id);
      setVersions(Array.isArray(data?.versions) ? data.versions : []);
      setActiveVersion(data?.active_version ?? null);
    } catch (err) {
      setError(err.message || "Failed to rename version");
    }
  };

  const handleDeleteVersion = async (versionNum) => {
    if (!workflow?.workflow_id) return;
    try {
      await deleteWorkflowVersion(workflow.workflow_id, versionNum);
      const data = await getWorkflowVersions(workflow.workflow_id);
      const list = Array.isArray(data?.versions) ? data.versions : [];
      setVersions(list);
      setActiveVersion(data?.active_version ?? null);
      if (versionNum === version) {
        const latest = list.slice().sort((a, b) => b.version - a.version)[0];
        if (latest) await loadVersion(latest.version);
      }
    } catch (err) {
      setError(err.message || "Failed to delete version");
    }
  };

  const handleActivateVersion = async (v) => {
    if (!workflow?.workflow_id) return;
    try {
      await activateWorkflowVersion(workflow.workflow_id, v.version);
      setActiveVersion(v.version);
      setStatusMessage(`Version ${v.version_label || "v" + v.version} is now active.`);
    } catch (err) {
      setError(err.message || "Failed to activate version");
    }
  };

  const s = {
    root: {
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: "#F6F2F4",
      zIndex: 1000,
      display: "flex",
      flexDirection: "column",
      fontFamily: "'Nunito Sans', 'Arial', sans-serif",
    },
    header: {
      padding: "12px 24px",
      backgroundColor: "#fff",
      borderBottom: "1px solid rgba(3,3,4,0.1)",
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      gap: "14px",
      flexWrap: "wrap",
      flexShrink: 0,
    },
    headerLeft: {
      display: "flex",
      alignItems: "center",
      gap: "16px",
      flexWrap: "wrap",
    },
    headerTitle: {
      fontSize: "18px",
      fontWeight: "700",
      color: "#030304",
      margin: 0,
    },
    headerMeta: { fontSize: "14px", color: "#9ca3af" },
    headerInput: {
      padding: "7px 10px",
      border: "1px solid rgba(3,3,4,0.1)",
      borderRadius: "6px",
      fontSize: "14px",
      width: "180px",
      boxSizing: "border-box",
    },
    headerActions: { display: "flex", gap: "10px", alignItems: "center" },
    btnCancel: {
      padding: "8px 18px",
      backgroundColor: "#f3f4f6",
      color: "#374151",
      border: "1px solid rgba(3,3,4,0.2)",
      borderRadius: "6px",
      cursor: "pointer",
      fontSize: "14px",
      fontWeight: "600",
    },
    btnSave: {
      padding: "8px 18px",
      background: "linear-gradient(135deg, #8DE971 0%, #7AC75E 100%)",
      color: "#030304",
      border: "none",
      borderRadius: "6px",
      cursor: "pointer",
      fontSize: "14px",
      fontWeight: "600",
    },
    body: { display: "flex", flex: 1, overflow: "hidden" },
    leftPanel: {
      width: "210px",
      flexShrink: 0,
      backgroundColor: "#fff",
      borderRight: "1px solid rgba(3,3,4,0.1)",
      display: "flex",
      flexDirection: "column",
      overflowY: "auto",
      overflowX: "hidden",
    },
    leftSection: { padding: "14px" },
    leftTitle: {
      fontSize: "12px",
      fontWeight: "700",
      color: "#9ca3af",
      textTransform: "uppercase",
      letterSpacing: "0.5px",
      marginBottom: "10px",
    },
    nodeChip: {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      padding: "9px 12px",
      marginBottom: "5px",
      backgroundColor: "#f9fafb",
      border: "1.5px dashed rgba(3,3,4,0.2)",
      borderRadius: "6px",
      cursor: "pointer",
      fontSize: "14px",
      fontWeight: "600",
      transition: "all 0.15s",
    },
    canvas: { flex: 1, position: "relative", minWidth: 0, overflow: "hidden" },
    rightPanel: {
      width: "300px",
      flexShrink: 0,
      backgroundColor: "#fff",
      borderLeft: "1px solid rgba(3,3,4,0.1)",
      display: "flex",
      flexDirection: "column",
      overflowY: "auto",
      overflowX: "hidden",
    },
    tabBar: {
      display: "flex",
      borderBottom: "1px solid rgba(3,3,4,0.1)",
      flexShrink: 0,
    },
    tab: {
      flex: 1,
      padding: "12px 0",
      textAlign: "center",
      fontSize: "14px",
      fontWeight: "600",
      cursor: "pointer",
      color: "#9ca3af",
      borderBottom: "2px solid transparent",
      transition: "all 0.15s",
      backgroundColor: "transparent",
      border: "none",
    },
    tabActive: {
      color: "#8DE971",
      borderBottom: "2px solid #8DE971",
    },
    rightContent: { flex: 1, overflowY: "auto" },
    overviewItem: {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      padding: "10px 14px",
      borderBottom: "1px solid rgba(3,3,4,0.06)",
      cursor: "pointer",
      transition: "all 0.15s",
    },
    dragHandle: {
      display: "flex",
      flexDirection: "column",
      gap: "2px",
      cursor: "grab",
      padding: "4px 2px",
      flexShrink: 0,
      opacity: 0.4,
      transition: "opacity 0.15s",
    },
    dragLine: {
      width: "14px",
      height: "2px",
      backgroundColor: "#9ca3af",
      borderRadius: "1px",
    },
    overviewIcon: {
      width: "30px",
      height: "30px",
      borderRadius: "6px",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: "14px",
      flexShrink: 0,
      color: "#fff",
      fontWeight: "700",
    },
    overviewText: { flex: 1, minWidth: 0 },
    overviewType: { fontSize: "14px", fontWeight: "700", color: "#374151" },
    overviewDesc: {
      fontSize: "13px",
      color: "#6b7280",
      marginTop: "2px",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis",
    },
    overviewDelete: {
      fontSize: "14px",
      color: "#d1d5db",
      cursor: "pointer",
      padding: "2px 6px",
      borderRadius: "3px",
      border: "none",
      backgroundColor: "transparent",
      lineHeight: 1,
    },
    statusBar: {
      padding: "8px 24px",
      backgroundColor: "#fff",
      borderTop: "1px solid rgba(3,3,4,0.1)",
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      fontSize: "13px",
      flexShrink: 0,
    },
    selectSmall: {
      padding: "7px 10px",
      border: "1px solid rgba(3,3,4,0.1)",
      borderRadius: "6px",
      fontSize: "14px",
      width: "100%",
      boxSizing: "border-box",
    },
    versionActionBtn: {
      fontSize: "11px",
      padding: "3px 10px",
      border: "1px solid rgba(3,3,4,0.1)",
      borderRadius: "4px",
      cursor: "pointer",
      backgroundColor: "#f9fafb",
      color: "#374151",
      fontWeight: "500",
    },
    emptyState: {
      padding: "24px 16px",
      textAlign: "center",
      color: "#9ca3af",
      fontSize: "14px",
    },
    /* ── BPMN Palette Styles ── */
    toolRow: {
      display: "flex",
      gap: "4px",
      padding: "10px 14px",
      borderBottom: "1px solid rgba(3,3,4,0.06)",
    },
    toolBtn: {
      flex: 1,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "8px 0",
      backgroundColor: "#f9fafb",
      border: "1.5px solid rgba(3,3,4,0.1)",
      borderRadius: "6px",
      cursor: "pointer",
      transition: "all 0.15s",
    },
    toolBtnActive: {
      backgroundColor: "rgba(141,233,113,0.1)",
      borderColor: "#8DE971",
      boxShadow: "0 1px 4px rgba(141,233,113,0.15)",
    },
    paletteSection: {
      padding: "14px",
      borderTop: "1px solid rgba(3,3,4,0.06)",
    },
    paletteHeader: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      cursor: "pointer",
      marginBottom: "8px",
      userSelect: "none",
    },
    paletteGrid: {
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gap: "6px",
    },
    paletteCategoryLabel: {
      fontSize: "10px",
      fontWeight: "700",
      color: "#9ca3af",
      textTransform: "uppercase",
      letterSpacing: "0.5px",
      marginBottom: "2px",
      marginTop: "8px",
      gridColumn: "1 / -1",
    },
    paletteIcon: {
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: "3px",
      padding: "8px 4px",
      backgroundColor: "#f9fafb",
      border: "1.5px solid rgba(3,3,4,0.1)",
      borderRadius: "6px",
      cursor: "pointer",
      transition: "all 0.15s",
      minHeight: "52px",
    },
    paletteIconLabel: {
      fontSize: "9px",
      fontWeight: "600",
      color: "#6b7280",
      textAlign: "center",
      lineHeight: "1.1",
    },
    paletteMoreBtn: {
      gridColumn: "1 / -1",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      gap: "4px",
      padding: "6px",
      backgroundColor: "transparent",
      border: "1px dashed rgba(3,3,4,0.2)",
      borderRadius: "6px",
      cursor: "pointer",
      fontSize: "11px",
      color: "#9ca3af",
      fontWeight: "600",
      marginTop: "4px",
      transition: "all 0.15s",
    },
    paletteSearchInput: {
      width: "100%",
      padding: "7px 10px 7px 30px",
      border: "1px solid rgba(3,3,4,0.1)",
      borderRadius: "6px",
      fontSize: "12px",
      boxSizing: "border-box",
      outline: "none",
      backgroundColor: "#f9fafb",
    },
    paletteSearchWrap: {
      position: "relative",
      marginBottom: "10px",
    },
    paletteSearchIcon: {
      position: "absolute",
      left: "9px",
      top: "0",
      bottom: "0",
      display: "flex",
      alignItems: "center",
      pointerEvents: "none",
    },
    toolLabel: {
      fontSize: "9px",
      fontWeight: "600",
      color: "#6b7280",
      marginTop: "3px",
      textAlign: "center",
    },
    contextPad: {
      position: "relative",
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gap: "3px",
      padding: "6px",
      backgroundColor: "#fff",
      border: "1px solid rgba(3,3,4,0.1)",
      borderRadius: "8px",
      boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
    },
    contextPadBtn: {
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      width: "32px",
      height: "32px",
      backgroundColor: "#f9fafb",
      border: "1px solid rgba(3,3,4,0.1)",
      borderRadius: "6px",
      cursor: "pointer",
      transition: "all 0.12s",
      padding: 0,
    },
  };

  const renderOverview = () => {
    const sortedNodes = getTopologicalOrder(nodes, edges, startNode);

    return (
      <div>
        {nodes.length === 0 ? (
          <div style={s.emptyState}>No nodes yet. Drag or click a node type from the left to add.</div>
        ) : (
          <>
            {sortedNodes.map((node, idx) => {
            const meta = NODE_META[node.type] || {
              icon: "?",
              color: "#6b7280",
              label: node.type,
            };
            const isStart = node.id === startNode;
            const isSelected = selectedNode?.id === node.id;
            const isDragOver = dragOverIdx === idx;

            return (
              <div
                key={node.id}
                draggable
                onDragStart={() => {
                  dragIdxRef.current = idx;
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOverIdx(idx);
                }}
                onDragLeave={() => {
                  setDragOverIdx(null);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  if (dragIdxRef.current !== null && dragIdxRef.current !== idx) {
                    handleOverviewReorder(dragIdxRef.current, idx);
                  }
                  dragIdxRef.current = null;
                  setDragOverIdx(null);
                }}
                onDragEnd={() => {
                  dragIdxRef.current = null;
                  setDragOverIdx(null);
                }}
                style={{
                  ...s.overviewItem,
                  backgroundColor: isDragOver ? "rgba(141,233,113,0.15)" : isSelected ? "rgba(141,233,113,0.08)" : "transparent",
                  borderTop: isDragOver ? "2px solid #8DE971" : "2px solid transparent",
                }}
                onClick={() => {
                  setSelectedNode(node);
                  setRightTab("edit");
                }}
                onMouseEnter={(e) => {
                  if (!isSelected && !isDragOver) e.currentTarget.style.backgroundColor = "#f9fafb";
                }}
                onMouseLeave={(e) => {
                  if (!isSelected && !isDragOver) e.currentTarget.style.backgroundColor = "transparent";
                }}
              >
                <div
                  style={s.dragHandle}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.opacity = "1";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.opacity = "0.4";
                  }}
                >
                  <div style={s.dragLine} />
                  <div style={s.dragLine} />
                  <div style={s.dragLine} />
                </div>

                <div style={{ ...s.overviewIcon, backgroundColor: meta.color }}>{meta.icon}</div>
                <div style={s.overviewText}>
                  <div style={s.overviewType}>
                    {idx + 1}. {meta.label}
                    {isStart && (
                      <span
                        style={{
                          fontSize: "10px",
                          color: "#8DE971",
                          marginLeft: "6px",
                          fontWeight: "600",
                        }}
                      >
                        START
                      </span>
                    )}
                  </div>
                  <div style={s.overviewDesc}>{getNodeDescription(node)}</div>
                </div>
                <button
                  style={s.overviewDelete}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteNode(node.id);
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = "#ef4444";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = "#d1d5db";
                  }}
                  title="Delete node"
                >
                  ✕
                </button>
              </div>
            );
          })}
          </>
        )}
      </div>
    );
  };

  const renderVersionsTab = () => {
    const sortedVersions = versions.slice().sort((a, b) => b.version - a.version);

    if (sortedVersions.length === 0) {
      return <div style={s.emptyState}>No versions yet. Save the workflow to create the first version.</div>;
    }

    return (
      <div>
        {sortedVersions.map((v) => {
          const isActive = v.version === activeVersion;
          const isCurrent = v.version === version;
          const isEditing = editingVersionLabel === v.version;
          const isConfirmingDelete = confirmDeleteVersion === v.version;
          const nodeCount = Array.isArray(v.nodes) ? v.nodes.length : 0;
          const dateStr = v.created_at ? new Date(v.created_at).toLocaleDateString() : "";

          return (
            <div
              key={v.version}
              style={{
                padding: "12px 14px",
                borderBottom: "1px solid rgba(3,3,4,0.06)",
                backgroundColor: isCurrent ? "rgba(141,233,113,0.06)" : "transparent",
              }}
            >
              {/* Row 1: Label + badges */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  marginBottom: "4px",
                  flexWrap: "wrap",
                }}
              >
                {isEditing ? (
                  <input
                    autoFocus
                    value={editLabelValue}
                    onChange={(e) => setEditLabelValue(e.target.value)}
                    onBlur={() => {
                      handleRenameVersion(v.version, editLabelValue);
                      setEditingVersionLabel(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        handleRenameVersion(v.version, editLabelValue);
                        setEditingVersionLabel(null);
                      }
                      if (e.key === "Escape") setEditingVersionLabel(null);
                    }}
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      padding: "2px 6px",
                      border: "1.5px solid #8DE971",
                      borderRadius: "4px",
                      outline: "none",
                      width: "120px",
                      fontFamily: "inherit",
                    }}
                  />
                ) : (
                  <span
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "#374151",
                      cursor: "pointer",
                    }}
                    title="Click to rename"
                    onClick={() => {
                      setEditingVersionLabel(v.version);
                      setEditLabelValue(v.version_label || `v${v.version}`);
                    }}
                  >
                    {v.version_label || `v${v.version}`}
                  </span>
                )}
                {isActive && (
                  <span
                    style={{
                      fontSize: "10px",
                      backgroundColor: "#d1fae5",
                      color: "#065f46",
                      padding: "1px 7px",
                      borderRadius: "9999px",
                      fontWeight: 600,
                    }}
                  >
                    Active
                  </span>
                )}
                {isCurrent && (
                  <span
                    style={{
                      fontSize: "10px",
                      backgroundColor: "rgba(141,233,113,0.15)",
                      color: "#6dd749",
                      padding: "1px 7px",
                      borderRadius: "9999px",
                      fontWeight: 600,
                    }}
                  >
                    Loaded
                  </span>
                )}
              </div>

              {/* Row 2: Metadata */}
              <div
                style={{
                  fontSize: "11px",
                  color: "#9ca3af",
                  marginBottom: "8px",
                }}
              >
                {dateStr}
                {dateStr && nodeCount > 0 ? " \u00b7 " : ""}
                {nodeCount > 0 ? `${nodeCount} nodes` : ""}
              </div>

              {/* Row 3: Actions */}
              {isConfirmingDelete ? (
                <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                  <span
                    style={{
                      fontSize: "12px",
                      color: "#dc2626",
                      fontWeight: 600,
                    }}
                  >
                    Delete?
                  </span>
                  <button
                    style={{
                      fontSize: "11px",
                      padding: "3px 10px",
                      backgroundColor: "#dc2626",
                      color: "#fff",
                      border: "none",
                      borderRadius: "4px",
                      cursor: "pointer",
                      fontWeight: 600,
                    }}
                    onClick={() => {
                      handleDeleteVersion(v.version);
                      setConfirmDeleteVersion(null);
                    }}
                  >
                    Yes
                  </button>
                  <button
                    style={{
                      fontSize: "11px",
                      padding: "3px 10px",
                      backgroundColor: "#f3f4f6",
                      color: "#374151",
                      border: "1px solid rgba(3,3,4,0.2)",
                      borderRadius: "4px",
                      cursor: "pointer",
                    }}
                    onClick={() => setConfirmDeleteVersion(null)}
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div style={{ display: "flex", gap: "6px" }}>
                  {!isCurrent && (
                    <button style={s.versionActionBtn} onClick={() => loadVersion(v.version)}>
                      Load
                    </button>
                  )}
                  {!isActive && (
                    <button
                      style={{
                        ...s.versionActionBtn,
                        backgroundColor: "#ecfdf5",
                        borderColor: "#6ee7b7",
                        color: "#065f46",
                        fontWeight: 600,
                      }}
                      onClick={() => handleActivateVersion(v)}
                    >
                      Activate
                    </button>
                  )}
                  {sortedVersions.length > 1 && (
                    <button
                      style={{
                        ...s.versionActionBtn,
                        color: "#ef4444",
                        borderColor: "#fecaca",
                      }}
                      onClick={() => setConfirmDeleteVersion(v.version)}
                    >
                      Delete
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div style={s.root}>
      {/* ─── Header ─── */}
      <div style={s.header}>
        <div style={s.headerLeft}>
          <h1 style={s.headerTitle}>{isEditMode ? "Edit Workflow" : "New Workflow"}</h1>
          <input
            style={{
              ...s.headerInput,
              ...(highlightFields.workflowId
                ? {
                    borderColor: "#ef4444",
                    boxShadow: "0 0 0 2px rgba(239,68,68,0.2)",
                  }
                : {}),
            }}
            value={workflowId}
            onChange={(e) => {
              setWorkflowId(e.target.value);
              setHighlightFields((h) => ({ ...h, workflowId: false }));
              setError("");
            }}
            disabled={isEditMode}
            placeholder="workflow_id"
          />
          <input
            style={{
              ...s.headerInput,
              ...(highlightFields.useCase
                ? {
                    borderColor: "#ef4444",
                    boxShadow: "0 0 0 2px rgba(239,68,68,0.2)",
                  }
                : {}),
            }}
            value={useCase}
            onChange={(e) => {
              setUseCase(e.target.value);
              setHighlightFields((h) => ({ ...h, useCase: false }));
              setError("");
            }}
            placeholder="use_case"
          />
          {isEditMode && (
            <span
              style={{
                ...s.headerInput,
                width: "auto",
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                color: "#374151",
                backgroundColor: "#f9fafb",
              }}
            >
              v{version}
              {activeVersion === version && (
                <span
                  style={{
                    fontSize: "11px",
                    backgroundColor: "#d1fae5",
                    color: "#065f46",
                    padding: "2px 8px",
                    borderRadius: "9999px",
                    fontWeight: 600,
                  }}
                >
                  Active
                </span>
              )}
            </span>
          )}
        </div>
        <div style={s.headerActions}>
          <button style={s.btnCancel} onClick={onClose}>
            Cancel
          </button>
          <button
            style={{
              ...s.btnSave,
              opacity: isSaving ? 0.6 : 1,
              cursor: isSaving ? "not-allowed" : "pointer",
            }}
            onClick={handleSaveWorkflow}
            disabled={isSaving}
          >
            {isSaving ? "Saving..." : "Save & Activate"}
          </button>
        </div>
      </div>

      {/* ─── Error / Success Banner ─── */}
      {error && (
        <div
          style={{
            padding: "8px 20px",
            backgroundColor: "#fef2f2",
            borderBottom: "1px solid #fecaca",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: "14px" }}>&#9888;</span>
          <span style={{ color: "#dc2626", fontSize: "13px", fontWeight: "600" }}>{error}</span>
          <button
            onClick={() => {
              setError("");
              setHighlightFields({});
            }}
            style={{
              marginLeft: "auto",
              background: "none",
              border: "none",
              color: "#dc2626",
              cursor: "pointer",
              fontSize: "14px",
            }}
          >
            &#10005;
          </button>
        </div>
      )}
      {statusMessage && (
        <div
          style={{
            padding: "8px 20px",
            backgroundColor: "#f0fdf4",
            borderBottom: "1px solid #bbf7d0",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            flexShrink: 0,
            animation: statusFading ? "statusFadeOut 0.5s ease-out forwards" : "statusSlideIn 0.3s ease-out forwards",
          }}
        >
          <style>{`
            @keyframes statusSlideIn {
              from { opacity: 0; transform: translateY(-100%); }
              to   { opacity: 1; transform: translateY(0); }
            }
            @keyframes statusFadeOut {
              from { opacity: 1; transform: translateY(0); }
              to   { opacity: 0; transform: translateY(-100%); }
            }
            @keyframes ghostFadeIn {
              from { opacity: 0; transform: scale(0.85); }
              to   { opacity: 0.85; transform: scale(1); }
            }
          `}</style>
          <span style={{ fontSize: "14px" }}>&#10003;</span>
          <span
            style={{
              color: "#16a34a",
              fontSize: "13px",
              fontWeight: "600",
              flex: 1,
            }}
          >
            {statusMessage}
          </span>
          <button
            onClick={() => setStatusMessage("")}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: "0 4px",
              fontSize: "16px",
              lineHeight: 1,
              color: "#16a34a",
              fontWeight: 700,
            }}
            title="Dismiss"
          >
            &times;
          </button>
        </div>
      )}

      {/* ─── Body ─── */}
      <div
        style={{
          padding: "14px 20px",
          background: safetyCriticalValidation
            ? "linear-gradient(135deg, #eff6ff 0%, #ecfeff 100%)"
            : "linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%)",
          borderBottom: "1px solid #dbeafe",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <span
            style={{
              fontSize: "11px",
              fontWeight: 800,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "#1d4ed8",
              backgroundColor: "#dbeafe",
              borderRadius: "999px",
              padding: "4px 10px",
            }}
          >
            Decision Validation Layer
          </span>
          <span style={{ fontSize: "13px", color: "#1e3a8a", fontWeight: 600 }}>
            Final outcomes are validated after the graph completes.
          </span>
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {[
            "Workflow outcome",
            "KB verification",
            "Risk calculation",
            "Final incident decision",
          ].map((step) => (
            <span
              key={step}
              style={{
                fontSize: "12px",
                color: "#1f2937",
                backgroundColor: "#ffffff",
                border: "1px solid rgba(59,130,246,0.16)",
                borderRadius: "999px",
                padding: "6px 10px",
                boxShadow: "0 10px 18px -20px rgba(15, 31, 51, 0.4)",
              }}
            >
              {step}
            </span>
          ))}
        </div>
        <div style={{ fontSize: "12px", color: "#334155", lineHeight: 1.55 }}>
          {safetyCriticalValidation
            ? "For safety-critical workflows, runtime combines the workflow outcome with Knowledge Base matches and calculated risk scores. If validation escalates severity, the more conservative decision wins."
            : "The workflow graph gathers structured facts first. Runtime validation then checks Knowledge Base evidence and recalculates risk before the incident is finalized."}
        </div>
      </div>

      <div style={s.body}>
        {/* Left Panel */}
        <div style={s.leftPanel}>
          {/* ─── Canvas Tools ─── */}
          <div style={s.toolRow}>
            {CANVAS_TOOLS.map((tool) => (
              <div
                key={tool.id}
                style={{
                  ...s.toolBtn,
                  flexDirection: "column",
                  ...(activeTool === tool.id ? s.toolBtnActive : {}),
                }}
                title={tool.title}
                onClick={() => {
                  setActiveTool((prev) => (prev === tool.id ? null : tool.id));
                  setConnectSource(null);
                  setContextPad(null);
                  setContextMoreOpen(false);
                  setContextColorOpen(false);
                }}
                onMouseEnter={(e) => {
                  if (activeTool !== tool.id) {
                    e.currentTarget.style.backgroundColor = "#FAF8F9";
                    e.currentTarget.style.borderColor = "rgba(3,3,4,0.15)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (activeTool !== tool.id) {
                    e.currentTarget.style.backgroundColor = "#f9fafb";
                    e.currentTarget.style.borderColor = "rgba(3,3,4,0.1)";
                  }
                }}
              >
                {tool.svg}
                <div style={s.toolLabel}>{tool.label}</div>
              </div>
            ))}
          </div>

          {/* ─── BPMN Node Palette ─── */}
          <div style={s.paletteSection}>
            <div style={s.paletteHeader} onClick={() => setPaletteOpen((prev) => !prev)}>
              <div style={s.leftTitle}>Node Palette</div>
              <span
                style={{
                  fontSize: "10px",
                  color: "#9ca3af",
                  transform: paletteOpen ? "rotate(180deg)" : "rotate(0deg)",
                  transition: "transform 0.2s",
                  display: "inline-block",
                }}
              >
                &#9660;
              </span>
            </div>

            {paletteOpen &&
              (() => {
                const q = paletteSearch.toLowerCase().trim();
                const filterItems = (items) =>
                  q
                    ? items.filter((it) => it.label.toLowerCase().includes(q) || it.type.toLowerCase().includes(q))
                    : items;
                const filterCats = (cats) =>
                  cats
                    .map((cat) => ({
                      ...cat,
                      items: q ? (cat.label.toLowerCase().includes(q) ? cat.items : filterItems(cat.items)) : cat.items,
                    }))
                    .filter((cat) => cat.items.length > 0);
                const filteredMain = filterCats(PALETTE_CATEGORIES);
                const filteredMore = filterCats(PALETTE_MORE_CATEGORIES);
                const showAll = q.length > 0;

                const renderPaletteItem = (item, idx) => {
                  const meta = NODE_META[item.type];
                  const svgKey = item.svgKey || item.type;
                  return (
                    <div
                      key={`${item.type}_${item.label}_${idx}`}
                      style={s.paletteIcon}
                      title={`Add ${item.label} node`}
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData("application/reactflow", item.type);
                        if (item.presetData)
                          e.dataTransfer.setData("application/preset", JSON.stringify(item.presetData));
                        e.dataTransfer.effectAllowed = "move";
                      }}
                      onClick={() => handleAddNode(item.type, item.presetData || {})}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = meta.color;
                        e.currentTarget.style.backgroundColor = "#fff";
                        e.currentTarget.style.boxShadow = `0 2px 8px ${meta.color}22`;
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = "rgba(3,3,4,0.1)";
                        e.currentTarget.style.backgroundColor = "#f9fafb";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    >
                      {PALETTE_SVG[svgKey] ? PALETTE_SVG[svgKey](meta.color) : PALETTE_SVG[item.type](meta.color)}
                      <span style={s.paletteIconLabel}>{item.label}</span>
                    </div>
                  );
                };

                return (
                  <>
                    {/* Search bar */}
                    <div style={s.paletteSearchWrap}>
                      <span style={s.paletteSearchIcon}>
                        <svg
                          width="13"
                          height="13"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="#9ca3af"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <circle cx="11" cy="11" r="8" />
                          <line x1="21" y1="21" x2="16.65" y2="16.65" />
                        </svg>
                      </span>
                      <input
                        style={s.paletteSearchInput}
                        placeholder="Search nodes..."
                        value={paletteSearch}
                        onChange={(e) => setPaletteSearch(e.target.value)}
                      />
                    </div>
                    <div style={s.paletteGrid}>
                      {filteredMain.map((cat) => (
                        <Fragment key={cat.label}>
                          <div style={s.paletteCategoryLabel}>{cat.label}</div>
                          {cat.items.map((item, idx) => renderPaletteItem(item, idx))}
                        </Fragment>
                      ))}

                      {!showAll && (
                        <button
                          style={s.paletteMoreBtn}
                          onClick={() => setPaletteMoreOpen((prev) => !prev)}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.borderColor = "#9ca3af";
                            e.currentTarget.style.color = "#6b7280";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.borderColor = "rgba(3,3,4,0.2)";
                            e.currentTarget.style.color = "#9ca3af";
                          }}
                        >
                          {paletteMoreOpen ? "− Less" : "··· More"}
                        </button>
                      )}

                      {(showAll || paletteMoreOpen) &&
                        filteredMore.map((cat) => (
                          <Fragment key={cat.label}>
                            <div style={s.paletteCategoryLabel}>{cat.label}</div>
                            {cat.items.map((item, idx) => renderPaletteItem(item, idx))}
                          </Fragment>
                        ))}

                      {q && filteredMain.length === 0 && filteredMore.length === 0 && (
                        <div
                          style={{
                            gridColumn: "1 / -1",
                            textAlign: "center",
                            color: "#9ca3af",
                            fontSize: "12px",
                            padding: "12px 0",
                          }}
                        >
                          No matching nodes
                        </div>
                      )}
                    </div>
                  </>
                );
              })()}
          </div>
        </div>

        {/* Canvas */}
        <div
          className={activeTool === "select" ? "rf-marquee-active" : ""}
          style={{
            ...s.canvas,
            cursor: activeTool
              ? { grab: "grab", select: "crosshair", connect: "pointer" }[activeTool] || "default"
              : "default",
          }}
          ref={reactFlowWrapper}
        >
          {/* Global cursor + node hover + marquee styling */}
          <style>{`
            .react-flow__node { cursor: pointer !important; }
            .react-flow__node:hover { cursor: pointer !important; }
            ${
              activeTool === "select"
                ? `
              .rf-marquee-active .react-flow__pane,
              .rf-marquee-active .react-flow__selectionpane,
              .rf-marquee-active .react-flow__selection {
                cursor: crosshair !important;
              }
              .rf-marquee-active .react-flow__selection {
                border: 2px dashed #8DE971 !important;
                background: rgba(141, 233, 113, 0.08) !important;
              }
            `
                : ""
            }
            ${
              !activeTool
                ? `
              .react-flow__pane { cursor: default !important; }
            `
                : ""
            }
            ${
              activeTool === "grab"
                ? `
              .react-flow__pane { cursor: grab !important; }
              .react-flow__pane:active { cursor: grabbing !important; }
            `
                : ""
            }
            ${
              activeTool === "connect"
                ? `
              .react-flow__pane { cursor: pointer !important; }
              .react-flow__node { cursor: pointer !important; }
              .react-flow__node:hover { cursor: pointer !important; }
            `
                : ""
            }
            ${
              connectSource
                ? `
              [data-id="${connectSource}"] > div {
                box-shadow: 0 0 0 3px rgba(141, 233, 113, 0.5) !important;
              }
            `
                : ""
            }
          `}</style>
          <ReactFlow
            nodes={visualNodes}
            edges={visualEdges}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodesDelete={onNodesDelete}
            onConnect={onConnect}
            deleteKeyCode={["Backspace", "Delete"]}
            onNodeClick={onNodeClick}
            onNodeMouseEnter={onNodeMouseEnter}
            onNodeMouseLeave={onNodeMouseLeave}
            onPaneClick={onPaneClick}
            onSelectionStart={() => {
              ignorePaneClickRef.current = true;
            }}
            onSelectionEnd={() => {
              setTimeout(() => {
                ignorePaneClickRef.current = false;
                setActiveTool(null);
              }, 50);
            }}
            onInit={(instance) => {
              setReactFlowInstance(instance);
              setTimeout(() => zoomToStart(instance, visualNodes, visualStartNodeId || startNode), 50);
            }}
            onDrop={onDrop}
            onDragOver={onDragOver}
            nodeTypes={nodeTypes}
            connectionLineType={ConnectionLineType.SmoothStep}
            panOnDrag={activeTool === "grab" || activeTool === null}
            selectionOnDrag={activeTool === "select"}
            connectOnClick={false}
            onSelectionChange={onSelectionChange}
            onMove={() => {
              if (contextPad) updateContextPadPosition(contextPad.nodeId);
            }}
            attributionPosition="bottom-left"
          >
            <Background color="rgba(3,3,4,0.08)" gap={20} />
            <Controls showInteractive={false} style={{ bottom: 12, left: 12 }} />
            <MiniMap
              nodeColor={(node) => NODE_META[node.type]?.color || "#6b7280"}
              maskColor="rgba(0,0,0,0.08)"
              style={{ width: 120, height: 80 }}
              pannable
              zoomable
            />
          </ReactFlow>

          {/* ─── Ghost Preview Node + Edge ─── */}
          {previewGhost &&
            reactFlowInstance &&
            (() => {
              const { x, y, zoom } = reactFlowInstance.getViewport();
              const screenX = previewGhost.position.x * zoom + x;
              const screenY = previewGhost.position.y * zoom + y;
              const meta = NODE_META[previewGhost.type];
              const isDiamond = previewGhost.type === "CONDITION" || previewGhost.type === "PARALLEL";
              const srcIsDiamond = previewGhost.sourceType === "CONDITION" || previewGhost.sourceType === "PARALLEL";
              const handle = previewGhost.sourceHandle;

              /* ── Compute source edge start point based on handle position ── */
              let srcScreenX, srcScreenY;
              if (srcIsDiamond) {
                // Diamond: top handle = "true"/"branch1", bottom handle = "false"/"branch2"
                const isTop = handle === "true" || handle === "branch1";
                srcScreenX = previewGhost.sourcePos.x * zoom + x + (previewGhost.sourceW * zoom) / 2;
                srcScreenY = previewGhost.sourcePos.y * zoom + y + (isTop ? 0 : previewGhost.sourceH * zoom);
              } else {
                // Rectangle: right side center
                srcScreenX = previewGhost.sourcePos.x * zoom + x + previewGhost.sourceW * zoom;
                srcScreenY = previewGhost.sourcePos.y * zoom + y + (previewGhost.sourceH * zoom) / 2;
              }

              /* ── Compute target edge end point ── */
              const tgtNodeH = isDiamond ? 96 : 44;
              const tgtScreenX = screenX;
              const tgtScreenY = screenY + (tgtNodeH * zoom) / 2;

              /* ── Build smoothstep (90° bend) path ── */
              let edgePath;
              if (srcIsDiamond) {
                // From top/bottom handle: go down/up, then right, then up/down to target left-center
                const isTop = handle === "true" || handle === "branch1";
                // Go vertical halfway to target Y, then horizontal to target, then vertical to target center
                const halfwayY = (srcScreenY + tgtScreenY) / 2;
                // Ensure minimum clearance from the diamond
                const minClearance = 40 * zoom;
                const bendY = isTop
                  ? Math.min(srcScreenY - minClearance, halfwayY)
                  : Math.max(srcScreenY + minClearance, halfwayY);
                edgePath = `M ${srcScreenX} ${srcScreenY} V ${bendY} H ${tgtScreenX} V ${tgtScreenY}`;
              } else {
                // From right handle: go horizontal, then vertical, then horizontal
                const midX = (srcScreenX + tgtScreenX) / 2;
                edgePath = `M ${srcScreenX} ${srcScreenY} H ${midX} V ${tgtScreenY} H ${tgtScreenX}`;
              }

              /* ── Arrow marker at end ── */
              const arrowSize = 8 * zoom;

              return (
                <Fragment>
                  {/* Ghost dashed edge */}
                  <svg
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      height: "100%",
                      pointerEvents: "none",
                      zIndex: 4,
                      overflow: "visible",
                    }}
                  >
                    <defs>
                      <marker
                        id="ghost-arrow"
                        viewBox="0 0 10 10"
                        refX="8"
                        refY="5"
                        markerWidth={arrowSize}
                        markerHeight={arrowSize}
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 0 L 10 5 L 0 10 z" fill={meta.color} opacity="0.6" />
                      </marker>
                    </defs>
                    <path
                      d={edgePath}
                      fill="none"
                      stroke={meta.color}
                      strokeWidth={1.5 * zoom}
                      strokeDasharray={`${6 * zoom} ${4 * zoom}`}
                      opacity="0.6"
                      markerEnd="url(#ghost-arrow)"
                      style={{ animation: "ghostFadeIn 0.2s ease-out" }}
                    />
                  </svg>

                  {/* Ghost node */}
                  <div
                    style={{
                      position: "absolute",
                      left: screenX,
                      top: screenY,
                      zIndex: 5,
                      pointerEvents: "none",
                      transform: `scale(${zoom})`,
                      transformOrigin: "top left",
                      animation: "ghostFadeIn 0.2s ease-out",
                    }}
                  >
                    {isDiamond ? (
                      /* ── Diamond ghost (CONDITION / PARALLEL) ── */
                      <div
                        style={{
                          width: "96px",
                          height: "96px",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        <div
                          style={{
                            width: "70px",
                            height: "70px",
                            transform: "rotate(45deg)",
                            border: `2px dashed ${meta.color}`,
                            backgroundColor: `${meta.color}10`,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            opacity: 0.85,
                          }}
                        >
                          <div
                            style={{
                              transform: "rotate(-45deg)",
                              textAlign: "center",
                              display: "flex",
                              flexDirection: "column",
                              alignItems: "center",
                              gap: "2px",
                            }}
                          >
                            <span style={{ display: "flex", transform: "scale(0.75)" }}>
                              {PALETTE_SVG[previewGhost.type](meta.color)}
                            </span>
                            <span
                              style={{
                                fontSize: "8px",
                                fontWeight: 700,
                                color: meta.color,
                              }}
                            >
                              {meta.label.toUpperCase()}
                            </span>
                          </div>
                        </div>
                      </div>
                    ) : (
                      /* ── Rounded rectangle ghost (all other nodes) ── */
                      <div
                        style={{
                          minWidth: "120px",
                          maxWidth: "160px",
                          padding: "8px 10px",
                          border: `2px dashed ${meta.color}`,
                          borderRadius: "6px",
                          backgroundColor: `${meta.color}10`,
                          opacity: 0.85,
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "6px",
                            marginBottom: "4px",
                          }}
                        >
                          <span style={{ display: "flex", transform: "scale(0.75)" }}>
                            {PALETTE_SVG[previewGhost.type](meta.color)}
                          </span>
                          <span
                            style={{
                              fontSize: "11px",
                              fontWeight: 600,
                              color: meta.color,
                            }}
                          >
                            {meta.label}
                          </span>
                        </div>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "3px",
                          }}
                        >
                          <span style={{ fontSize: "7px" }}>{meta.icon}</span>
                          <span
                            style={{
                              fontSize: "7px",
                              fontWeight: 600,
                              color: meta.color,
                              textTransform: "uppercase",
                            }}
                          >
                            {previewGhost.type.replace("_", " ")}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </Fragment>
              );
            })()}

          {/* ─── Node Context Pad ─── */}
          {contextPad && activeTool !== "select" && (
            <div
              style={{
                position: "absolute",
                left: contextPad.x,
                top: contextPad.y,
                zIndex: 20,
                transform: "translateX(-50%)",
              }}
              onMouseDown={(e) => e.stopPropagation()}
              onMouseEnter={() => {
                if (hideContextPadRef.current) {
                  clearTimeout(hideContextPadRef.current);
                  hideContextPadRef.current = null;
                }
              }}
              onMouseLeave={() => {
                hideContextPadRef.current = setTimeout(() => {
                  setContextPad(null);
                  setContextMoreOpen(false);
                  setContextColorOpen(false);
                  setContextMoreSearch("");
                }, 200);
              }}
            >
              <div style={s.contextPad}>
                {/* Quick-add nodes */}
                {[
                  { type: "QUESTION", tip: "Add Question" },
                  { type: "CONDITION", tip: "Add Condition" },
                  { type: "DECISION", tip: "Add Decision" },
                ].map((qa) => (
                  <button
                    key={qa.type}
                    style={s.contextPadBtn}
                    title={qa.tip}
                    onClick={() => handleQuickAdd(contextPad.nodeId, qa.type)}
                    onMouseEnter={(e) => {
                      setContextColorOpen(false);
                      setContextMoreOpen(false);
                      e.currentTarget.style.borderColor = NODE_META[qa.type].color;
                      e.currentTarget.style.backgroundColor = "#fff";
                      showPreviewGhost(contextPad.nodeId, qa.type);
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = "rgba(3,3,4,0.1)";
                      e.currentTarget.style.backgroundColor = "#f9fafb";
                      setPreviewGhost(null);
                    }}
                  >
                    <span style={{ transform: "scale(0.75)", display: "flex" }}>
                      {PALETTE_SVG[qa.type](NODE_META[qa.type].color)}
                    </span>
                  </button>
                ))}
                {/* Delete button */}
                <button
                  style={s.contextPadBtn}
                  title="Delete node"
                  onClick={() => {
                    handleDeleteNode(contextPad.nodeId);
                    setContextPad(null);
                  }}
                  onMouseEnter={(e) => {
                    setContextColorOpen(false);
                    setContextMoreOpen(false);
                    e.currentTarget.style.borderColor = "#ef4444";
                    e.currentTarget.style.backgroundColor = "#fef2f2";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "rgba(3,3,4,0.1)";
                    e.currentTarget.style.backgroundColor = "#f9fafb";
                  }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#ef4444"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
                {/* Set color button */}
                <button
                  style={s.contextPadBtn}
                  title="Set node color"
                  onClick={() => {
                    setContextColorOpen((prev) => !prev);
                    setContextMoreOpen(false);
                  }}
                  onMouseEnter={(e) => {
                    setContextMoreOpen(false);
                    e.currentTarget.style.borderColor = "#8b5cf6";
                    e.currentTarget.style.backgroundColor = "#faf5ff";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "rgba(3,3,4,0.1)";
                    e.currentTarget.style.backgroundColor = "#f9fafb";
                  }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#8b5cf6"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M12 2a10 10 0 0 0 0 20 2 2 0 0 0 2-2v-1a2 2 0 0 1 2-2h1a2 2 0 0 0 2-2 10 10 0 0 0-7-13z" />
                    <circle cx="8" cy="12" r="1.5" fill="#ef4444" stroke="none" />
                    <circle cx="12" cy="8" r="1.5" fill="#f59e0b" stroke="none" />
                    <circle cx="16" cy="12" r="1.5" fill="#10b981" stroke="none" />
                  </svg>
                </button>
                {/* More button */}
                <button
                  style={s.contextPadBtn}
                  title="More nodes"
                  onClick={() => {
                    setContextMoreOpen((prev) => {
                      if (prev) setContextMoreSearch("");
                      return !prev;
                    });
                    setContextColorOpen(false);
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = "#6b7280";
                    e.currentTarget.style.backgroundColor = "#f3f4f6";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "rgba(3,3,4,0.1)";
                    e.currentTarget.style.backgroundColor = "#f9fafb";
                  }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#374151"
                    strokeWidth="2"
                    strokeLinecap="round"
                  >
                    <circle cx="5" cy="12" r="1.5" fill="#374151" />
                    <circle cx="12" cy="12" r="1.5" fill="#374151" />
                    <circle cx="19" cy="12" r="1.5" fill="#374151" />
                  </svg>
                </button>
              </div>

              {/* ─── Color Picker Popover ─── */}
              {contextColorOpen && (
                <div
                  style={{
                    position: "absolute",
                    left: "100%",
                    top: 0,
                    marginLeft: "4px",
                    display: "grid",
                    gridTemplateColumns: "repeat(3, 1fr)",
                    gap: "3px",
                    padding: "6px",
                    backgroundColor: "#fff",
                    border: "1px solid rgba(3,3,4,0.1)",
                    borderRadius: "8px",
                    boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
                    zIndex: 30,
                  }}
                  onMouseEnter={() => {
                    if (hideContextPadRef.current) {
                      clearTimeout(hideContextPadRef.current);
                      hideContextPadRef.current = null;
                    }
                  }}
                  onMouseLeave={() => {
                    hideContextPadRef.current = setTimeout(() => {
                      setContextPad(null);
                      setContextMoreOpen(false);
                      setContextColorOpen(false);
                    }, 200);
                  }}
                >
                  {COLOR_CHOICES.map((color) => (
                    <div
                      key={color.value}
                      title={color.name}
                      aria-label={color.name}
                      onClick={() => {
                        handleNodeColorChange(contextPad.nodeId, color.value);
                        setContextColorOpen(false);
                      }}
                      style={{
                        width: "32px",
                        height: "32px",
                        borderRadius: "50%",
                        backgroundColor: color.value,
                        cursor: "pointer",
                        border: "2px solid transparent",
                        transition: "transform 0.12s",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = "scale(1.2)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = "scale(1)";
                      }}
                    />
                  ))}
                </div>
              )}

              {/* ─── More Nodes Popover ─── */}
              {contextMoreOpen &&
                (() => {
                  const sections = [
                    {
                      name: "Tasks",
                      types: ["QUESTION", "CALCULATE", "ML_MODEL", "HUMAN_OVERRIDE", "SUB_WORKFLOW"],
                    },
                    { name: "Gateways", types: ["CONDITION", "PARALLEL"] },
                    { name: "Events", types: ["DECISION", "WAIT"] },
                  ];
                  const defaultTypes = ["CALCULATE", "ML_MODEL", "HUMAN_OVERRIDE", "SUB_WORKFLOW"];
                  const query = contextMoreSearch.toLowerCase().trim();
                  const isSearching = query.length > 0;

                  let searchResults = [];
                  if (isSearching) {
                    // Check if query matches a section name — show all nodes in that section
                    const matchedSection = sections.find((sec) => sec.name.toLowerCase().includes(query));
                    if (matchedSection) {
                      searchResults = matchedSection.types;
                    } else {
                      // Filter all node types by label
                      searchResults = NODE_TYPES.filter((t) => NODE_META[t].label.toLowerCase().includes(query));
                    }
                  }

                  const displayTypes = isSearching ? searchResults : defaultTypes;

                  return (
                    <div
                      style={{
                        position: "absolute",
                        left: "100%",
                        top: 0,
                        marginLeft: "6px",
                        padding: "6px",
                        backgroundColor: "#fff",
                        border: "1px solid rgba(3,3,4,0.1)",
                        borderRadius: "8px",
                        boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
                        minWidth: "150px",
                        maxWidth: "200px",
                      }}
                    >
                      {/* Search bar */}
                      <div style={{ position: "relative", marginBottom: "6px" }}>
                        <svg
                          width="12"
                          height="12"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="#9ca3af"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          style={{
                            position: "absolute",
                            left: "6px",
                            top: "50%",
                            transform: "translateY(-50%)",
                          }}
                        >
                          <circle cx="11" cy="11" r="8" />
                          <line x1="21" y1="21" x2="16.65" y2="16.65" />
                        </svg>
                        <input
                          type="text"
                          placeholder="Search nodes..."
                          value={contextMoreSearch}
                          onChange={(e) => setContextMoreSearch(e.target.value)}
                          autoFocus
                          style={{
                            width: "100%",
                            boxSizing: "border-box",
                            padding: "5px 6px 5px 22px",
                            fontSize: "10px",
                            border: "1px solid rgba(3,3,4,0.1)",
                            borderRadius: "5px",
                            outline: "none",
                            backgroundColor: "#f9fafb",
                            color: "#374151",
                            fontFamily: "inherit",
                          }}
                          onFocus={(e) => {
                            e.target.style.borderColor = "#8DE971";
                          }}
                          onBlur={(e) => {
                            e.target.style.borderColor = "rgba(3,3,4,0.1)";
                          }}
                        />
                      </div>
                      {/* Section label when searching */}
                      {isSearching &&
                        searchResults.length > 0 &&
                        (() => {
                          const matchedSection = sections.find((sec) => sec.name.toLowerCase().includes(query));
                          return matchedSection ? (
                            <div
                              style={{
                                fontSize: "8px",
                                fontWeight: "700",
                                color: "#9ca3af",
                                textTransform: "uppercase",
                                letterSpacing: "0.5px",
                                padding: "2px 2px 4px",
                                borderBottom: "1px solid rgba(3,3,4,0.06)",
                                marginBottom: "4px",
                              }}
                            >
                              {matchedSection.name}
                            </div>
                          ) : null;
                        })()}
                      {/* Node list */}
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: "2px",
                        }}
                      >
                        {displayTypes.length > 0 ? (
                          displayTypes.map((type) => (
                            <button
                              key={type}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "6px",
                                padding: "4px 6px",
                                border: "1px solid rgba(3,3,4,0.1)",
                                borderRadius: "5px",
                                backgroundColor: "#f9fafb",
                                cursor: "pointer",
                                transition: "all 0.15s",
                                width: "100%",
                                textAlign: "left",
                              }}
                              title={`Add ${NODE_META[type].label}`}
                              onClick={() => {
                                handleQuickAdd(contextPad.nodeId, type);
                                setContextMoreOpen(false);
                                setContextMoreSearch("");
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.borderColor = NODE_META[type].color;
                                e.currentTarget.style.backgroundColor = "#fff";
                                showPreviewGhost(contextPad.nodeId, type);
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.borderColor = "rgba(3,3,4,0.1)";
                                e.currentTarget.style.backgroundColor = "#f9fafb";
                                setPreviewGhost(null);
                              }}
                            >
                              <span
                                style={{
                                  transform: "scale(0.6)",
                                  display: "flex",
                                  flexShrink: 0,
                                }}
                              >
                                {PALETTE_SVG[type](NODE_META[type].color)}
                              </span>
                              <span
                                style={{
                                  fontSize: "9px",
                                  fontWeight: "500",
                                  color: "#374151",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                {NODE_META[type].label}
                              </span>
                            </button>
                          ))
                        ) : (
                          <div
                            style={{
                              fontSize: "9px",
                              color: "#9ca3af",
                              textAlign: "center",
                              padding: "6px 0",
                            }}
                          >
                            No nodes found
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })()}
            </div>
          )}

          {/* ─── Selection Context Pad (marquee multi-select) ─── */}
          {selectionPad && (
            <div
              style={{
                position: "absolute",
                left: selectionPad.x,
                top: selectionPad.y,
                zIndex: 20,
              }}
              onMouseDown={(e) => e.stopPropagation()}
            >
              <div
                style={{
                  ...s.contextPad,
                  gridTemplateColumns: "repeat(2, 1fr)",
                }}
              >
                {/* Delete selected */}
                <button
                  style={s.contextPadBtn}
                  title={`Delete ${selectionPad.nodeIds.length} nodes`}
                  onClick={() => handleDeleteSelectedNodes(selectionPad.nodeIds)}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = "#ef4444";
                    e.currentTarget.style.backgroundColor = "#fef2f2";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "rgba(3,3,4,0.1)";
                    e.currentTarget.style.backgroundColor = "#f9fafb";
                  }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#ef4444"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
                {/* Set color for selected */}
                <button
                  style={s.contextPadBtn}
                  title="Set color for selected nodes"
                  onClick={() => setSelectionColorOpen((prev) => !prev)}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = "#8b5cf6";
                    e.currentTarget.style.backgroundColor = "#faf5ff";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "rgba(3,3,4,0.1)";
                    e.currentTarget.style.backgroundColor = "#f9fafb";
                  }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#8b5cf6"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M12 2a10 10 0 0 0 0 20 2 2 0 0 0 2-2v-1a2 2 0 0 1 2-2h1a2 2 0 0 0 2-2 10 10 0 0 0-7-13z" />
                    <circle cx="8" cy="12" r="1.5" fill="#ef4444" stroke="none" />
                    <circle cx="12" cy="8" r="1.5" fill="#f59e0b" stroke="none" />
                    <circle cx="16" cy="12" r="1.5" fill="#10b981" stroke="none" />
                  </svg>
                </button>
              </div>

              {/* Color picker for selection */}
              {selectionColorOpen && (
                <div
                  style={{
                    position: "absolute",
                    left: "100%",
                    top: 0,
                    marginLeft: "4px",
                    display: "grid",
                    gridTemplateColumns: "repeat(3, 1fr)",
                    gap: "3px",
                    padding: "6px",
                    backgroundColor: "#fff",
                    border: "1px solid rgba(3,3,4,0.1)",
                    borderRadius: "8px",
                    boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
                    zIndex: 30,
                  }}
                >
                  {["#dbeafe", "#d1fae5", "#fef3c7", "#fee2e2", "#ede9fe", "#fce7f3"].map((color) => (
                    <div
                      key={color}
                      onClick={() => {
                        handleNodeColorChange(selectionPad.nodeIds, color);
                        setSelectionColorOpen(false);
                      }}
                      style={{
                        width: "32px",
                        height: "32px",
                        borderRadius: "50%",
                        backgroundColor: color,
                        cursor: "pointer",
                        border: "2px solid rgba(3,3,4,0.2)",
                        transition: "transform 0.12s",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = "scale(1.2)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = "scale(1)";
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Panel */}
        <div style={s.rightPanel}>
          <div style={s.tabBar}>
            <button
              style={{
                ...s.tab,
                ...(rightTab === "overview" ? s.tabActive : {}),
              }}
              onClick={() => setRightTab("overview")}
            >
              Overview ({nodes.length})
            </button>
            <button
              style={{ ...s.tab, ...(rightTab === "edit" ? s.tabActive : {}) }}
              onClick={() => setRightTab("edit")}
            >
              Edit Node
            </button>
            <button
              style={{
                ...s.tab,
                ...(rightTab === "versions" ? s.tabActive : {}),
              }}
              onClick={() => setRightTab("versions")}
            >
              Versions ({versions.length})
            </button>
          </div>
          <div style={s.rightContent}>
            {rightTab === "overview" ? (
              renderOverview()
            ) : rightTab === "versions" ? (
              renderVersionsTab()
            ) : (
              <NodePropertiesForm node={selectedNode} onChange={handleNodeDataChange} onDelete={handleDeleteNode} allNodes={nodes} />
            )}
          </div>
        </div>
      </div>

      {/* ─── Status Bar ─── */}
      <div style={s.statusBar}>
        <span style={{ color: "#9ca3af" }}>Drag nodes onto canvas or click to add &middot; Click a node to edit</span>
      </div>
    </div>
  );
};

export default WorkflowBuilderVisual;
