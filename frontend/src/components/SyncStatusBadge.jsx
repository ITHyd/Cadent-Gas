/**
 * SyncStatusBadge — inline pill badge showing connector sync state on incident rows/cards.
 *
 * Props:
 *   externalRef  — the incident's `external_ref` object (or null/undefined)
 *     Expected shape: { external_id, external_number, sync_status, external_url }
 *
 * Renders nothing if externalRef is falsy or empty.
 */
import React from 'react';

const STATUS_CONFIG = {
  linked: {
    bg: '#f0fdf4',
    color: '#047857',
    dot: '#047857',
    label: null, // uses external_number
  },
  synced: {
    bg: '#f0fdf4',
    color: '#047857',
    dot: '#047857',
    label: null,
  },
  pending: {
    bg: '#fffbeb',
    color: '#b45309',
    dot: '#f59e0b',
    label: 'Syncing…',
  },
  syncing: {
    bg: '#fffbeb',
    color: '#b45309',
    dot: '#f59e0b',
    label: 'Syncing…',
  },
  error: {
    bg: '#fef2f2',
    color: '#b91c1c',
    dot: '#ef4444',
    label: 'Sync Error',
  },
};

const DEFAULT_CONFIG = {
  bg: '#f1f5f9',
  color: 'rgba(3,3,4,0.7)',
  dot: '#94a3b8',
  label: 'Unknown',
};

const CONNECTOR_LABELS = {
  servicenow: 'SN',
  sap: 'SAP',
  jira: 'Jira',
  aws: 'AWS',
  zendesk: 'Zendesk',
};

export default function SyncStatusBadge({ externalRef }) {
  if (!externalRef || typeof externalRef !== 'object') return null;

  const syncStatus = externalRef.sync_status || 'linked';
  const config = STATUS_CONFIG[syncStatus] || DEFAULT_CONFIG;
  const connectorLabel = CONNECTOR_LABELS[externalRef.connector_type] || externalRef.connector_type || 'Ext';
  const displayText = config.label || externalRef.external_number || connectorLabel;
  const prefix = !config.label ? `${connectorLabel}: ` : '';

  const badge = (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '5px',
        borderRadius: '999px',
        padding: '3px 9px',
        background: config.bg,
        color: config.color,
        fontSize: '0.72rem',
        fontWeight: 700,
        lineHeight: 1.3,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: '999px',
          background: config.dot,
          flexShrink: 0,
        }}
      />
      {prefix}{displayText}
    </span>
  );

  if (externalRef.external_url) {
    return (
      <a
        href={externalRef.external_url}
        target="_blank"
        rel="noopener noreferrer"
        style={{ textDecoration: 'none' }}
        title={`Open in ${CONNECTOR_LABELS[externalRef.connector_type] || externalRef.connector_type || 'external system'}: ${externalRef.external_number || externalRef.external_id || ''}`}
      >
        {badge}
      </a>
    );
  }

  return badge;
}
