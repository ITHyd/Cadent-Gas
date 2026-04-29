import { useEffect, useMemo, useState } from 'react';
import {
  getKBStats,
  getTenants,
  getTenantWorkflows,
  getTrueIncidentsKB,
  getFalseIncidentsKB,
} from '../services/api';
import {
  BubbleChart,
  DateRangeSelector,
  DonutChart,
  LineTrendChart,
  TrendBadge,
} from '../components/ModernDashboardCharts';

const formatLabel = (value) => {
  if (!value) return 'Unknown';
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const getRatio = (value, total) => {
  if (!total) return 0;
  return Math.max(0, Math.min(100, Math.round((value / total) * 100)));
};

const getRangeBounds = (dateRange, customStartDate, customEndDate) => {
  const end = customEndDate ? new Date(`${customEndDate}T23:59:59`) : new Date();
  if (dateRange === 'custom' && customStartDate) {
    return {
      start: new Date(`${customStartDate}T00:00:00`),
      end,
    };
  }

  const dayMap = { '7d': 7, '30d': 30, '90d': 90 };
  const days = dayMap[dateRange] || 30;
  const start = new Date(end);
  start.setDate(end.getDate() - days + 1);
  start.setHours(0, 0, 0, 0);
  return { start, end };
};

const isWithinRange = (value, start, end) => {
  if (!value) return false;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return false;
  return parsed >= start && parsed <= end;
};

const getPreviousRangeBounds = (dateRange, customStartDate, customEndDate) => {
  const { start, end } = getRangeBounds(dateRange, customStartDate, customEndDate);
  const durationMs = Math.max(86400000, end.getTime() - start.getTime() + 1);
  const prevEnd = new Date(start.getTime() - 1);
  const prevStart = new Date(prevEnd.getTime() - durationMs + 1);
  return { start: prevStart, end: prevEnd };
};

const trendDelta = (current, previous) => {
  if (!previous) return current ? 100 : 0;
  return Math.round(((current - previous) / previous) * 100);
};

const SuperUserDashboard = () => {
  const [tenants, setTenants] = useState([]);
  const [, setKbStats] = useState({ total_true: 0, total_false: 0 });
  const [trueKbEntries, setTrueKbEntries] = useState([]);
  const [falseKbEntries, setFalseKbEntries] = useState([]);
  const [tenantKbStats, setTenantKbStats] = useState({});
  const [tenantWorkflows, setTenantWorkflows] = useState({});
  const [dateRange, setDateRange] = useState('30d');
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');

  useEffect(() => {
    const fetchStats = async () => {
      const [kbResult, tenantResult, trueKbResult, falseKbResult] = await Promise.allSettled([
        getKBStats(),
        getTenants(),
        getTrueIncidentsKB(1, 500),
        getFalseIncidentsKB(1, 500),
      ]);

      const kbData = kbResult.status === 'fulfilled' ? kbResult.value : { total_true: 0, total_false: 0 };
      const tenantData = tenantResult.status === 'fulfilled' ? tenantResult.value : { tenants: [] };
      const trueKbData = trueKbResult.status === 'fulfilled' ? trueKbResult.value : { items: [] };
      const falseKbData = falseKbResult.status === 'fulfilled' ? falseKbResult.value : { items: [] };

      const tenantList = tenantData?.tenants || [];
      setKbStats({
        total_true: kbData?.total_true || 0,
        total_false: kbData?.total_false || 0,
      });
      setTrueKbEntries(trueKbData.items || []);
      setFalseKbEntries(falseKbData.items || []);
      setTenants(tenantList);

      const kbByTenant = {};
      const workflowsByTenant = {};
      await Promise.allSettled(
        tenantList.map(async (tenant) => {
          const [tenantKb, workflows] = await Promise.all([
            getKBStats(tenant.tenant_id).catch(() => ({ total_true: 0, total_false: 0 })),
            getTenantWorkflows(tenant.tenant_id).catch(() => []),
          ]);
          kbByTenant[tenant.tenant_id] = tenantKb;
          workflowsByTenant[tenant.tenant_id] = Array.isArray(workflows) ? workflows : [];
        })
      );
      setTenantKbStats(kbByTenant);
      setTenantWorkflows(workflowsByTenant);
    };

    fetchStats();
  }, []);

  const analytics = useMemo(() => {
    const range = getRangeBounds(dateRange, customStartDate, customEndDate);
    const previousRange = getPreviousRangeBounds(dateRange, customStartDate, customEndDate);

    // Tenant/workflow portfolio metrics should reflect the current platform
    // state, not disappear just because the records were created before the
    // selected reporting window. Keep the time filter for dated KB analytics.
    const filteredTenants = tenants;
    const filteredTrueKb = trueKbEntries.filter((entry) => isWithinRange(entry.created_at, range.start, range.end));
    const filteredFalseKb = falseKbEntries.filter((entry) => isWithinRange(entry.created_at, range.start, range.end));
    const previousTrueKb = trueKbEntries.filter((entry) => isWithinRange(entry.created_at, previousRange.start, previousRange.end));
    const previousFalseKb = falseKbEntries.filter((entry) => isWithinRange(entry.created_at, previousRange.start, previousRange.end));

    const workflowRecords = filteredTenants.flatMap((tenant) =>
      (tenantWorkflows[tenant.tenant_id] || [])
        .map((workflow) => ({
          ...workflow,
          tenant_id: tenant.tenant_id,
          tenant_name: tenant.display_name || tenant.tenant_id,
          incident_volume: tenant.incidents?.total || 0,
          false_ratio: getRatio(
            tenantKbStats[tenant.tenant_id]?.total_false || 0,
            (tenantKbStats[tenant.tenant_id]?.total_true || 0) + (tenantKbStats[tenant.tenant_id]?.total_false || 0)
          ),
        }))
    );

    const filteredWorkflowCount = workflowRecords.length;
    const filteredWorkflowUseCases = new Set(workflowRecords.map((workflow) => workflow.use_case).filter(Boolean)).size;
    const incidentVolume = filteredTenants.reduce((sum, tenant) => sum + (tenant.incidents?.total || 0), 0);
    const activeTenants = filteredTenants.filter((tenant) => tenant.status === 'active').length;

    const lineBucketCount = dateRange === '7d' ? 7 : dateRange === '90d' ? 12 : 10;
    const lineLabels = [];
    const trueSeries = [];
    const falseSeries = [];
    for (let index = lineBucketCount - 1; index >= 0; index -= 1) {
      const bucketStart = new Date(range.end);
      bucketStart.setDate(range.end.getDate() - index * Math.ceil((dateRange === '90d' ? 90 : dateRange === '7d' ? 7 : 30) / lineBucketCount));
      bucketStart.setHours(0, 0, 0, 0);
      const bucketEnd = new Date(bucketStart);
      bucketEnd.setDate(bucketStart.getDate() + Math.ceil((dateRange === '90d' ? 90 : dateRange === '7d' ? 7 : 30) / lineBucketCount) - 1);
      bucketEnd.setHours(23, 59, 59, 999);
      lineLabels.push(`${bucketStart.getDate()}/${bucketStart.getMonth() + 1}`);
      trueSeries.push(filteredTrueKb.filter((entry) => isWithinRange(entry.created_at, bucketStart, bucketEnd)).length);
      falseSeries.push(filteredFalseKb.filter((entry) => isWithinRange(entry.created_at, bucketStart, bucketEnd)).length);
    }

    return {
      rangeLabel: `${range.start.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })} - ${range.end.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}`,
      totalTenants: filteredTenants.length,
      activeTenants,
      totalWorkflows: filteredWorkflowCount,
      workflowUseCases: filteredWorkflowUseCases,
      incidentVolume,
      kbTrue: filteredTrueKb.length,
      kbFalse: filteredFalseKb.length,
      trueTrendDelta: trendDelta(filteredTrueKb.length, previousTrueKb.length),
      falseTrendDelta: trendDelta(filteredFalseKb.length, previousFalseKb.length),
      kbDonutSegments: [
        { label: 'True Patterns', value: filteredTrueKb.length, color: '#10b981' },
        { label: 'False Patterns', value: filteredFalseKb.length, color: '#ef4444' },
      ],
      kbLine: {
        labels: lineLabels,
        series: [
          { label: 'True', values: trueSeries, color: '#10b981' },
          { label: 'False', values: falseSeries, color: '#ef4444' },
        ],
      },
      bubblePoints: filteredTenants.map((tenant) => {
        const kb = tenantKbStats[tenant.tenant_id] || { total_true: 0, total_false: 0 };
        const totalKb = (kb.total_true || 0) + (kb.total_false || 0);
        const workflowCount = (tenantWorkflows[tenant.tenant_id] || []).length;
        return {
          id: tenant.tenant_id,
          shortLabel: (tenant.display_name || tenant.tenant_id).slice(0, 3).toUpperCase(),
          x: workflowCount,
          y: totalKb ? (kb.total_false || 0) / totalKb : 0,
          size: tenant.incidents?.total || 1,
          color: tenant.status === 'active' ? '#38bdf8' : '#cbd5e1',
        };
      }),
      leaderboard: workflowRecords
        .slice()
        .sort((left, right) => {
          const leftNodes = Array.isArray(left.nodes) ? left.nodes.length : left.nodes || 0;
          const rightNodes = Array.isArray(right.nodes) ? right.nodes.length : right.nodes || 0;
          return rightNodes - leftNodes;
        })
        .slice(0, 8)
        .map((workflow) => ({
          workflow_id: workflow.workflow_id,
          tenant_name: workflow.tenant_name,
          use_case: formatLabel(workflow.use_case),
          version: workflow.version,
          nodes: Array.isArray(workflow.nodes) ? workflow.nodes.length : workflow.nodes || 0,
          incident_volume: workflow.incident_volume,
          false_ratio: workflow.false_ratio,
          created_at: workflow.created_at,
        })),
    };
  }, [customEndDate, customStartDate, dateRange, falseKbEntries, tenantKbStats, tenantWorkflows, tenants, trueKbEntries]);

  const styles = {
    container: {
      minHeight: '100vh',
      background: 'linear-gradient(180deg, #eef4fb 0%, #f8fafc 38%, #f1f5f9 100%)',
      padding: '2rem 2.5rem 2.5rem',
    },
    shell: {
      maxWidth: '1440px',
      margin: '0 auto',
    },
    header: {
      marginBottom: '1.1rem',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      gap: '14px',
      flexWrap: 'wrap',
    },
    title: {
      fontSize: '2rem',
      fontWeight: 800,
      color: '#0f172a',
      marginBottom: '0.5rem',
    },
    subtitle: {
      color: '#64748b',
      maxWidth: '760px',
      margin: 0,
      lineHeight: 1.6,
    },
    statGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
      gap: '1rem',
      marginBottom: '1rem',
    },
    statCard: {
      background: 'rgba(255,255,255,0.96)',
      borderRadius: '1rem',
      padding: '1.25rem',
      border: '1px solid rgba(148, 163, 184, 0.18)',
      boxShadow: '0 14px 40px -30px rgba(15, 23, 42, 0.45)',
    },
    statValue: {
      fontSize: '2.2rem',
      fontWeight: 800,
      lineHeight: 1,
      marginBottom: '0.6rem',
    },
    statLabel: {
      color: '#64748b',
      fontSize: '0.9rem',
      fontWeight: 600,
    },
    panel: {
      background: 'rgba(255,255,255,0.96)',
      borderRadius: '1.15rem',
      padding: '1.25rem',
      border: '1px solid rgba(148, 163, 184, 0.18)',
      boxShadow: '0 14px 40px -30px rgba(15, 23, 42, 0.4)',
      minHeight: '100%',
    },
    panelTitle: {
      margin: 0,
      color: '#0f172a',
      fontSize: '1rem',
      fontWeight: 800,
    },
    panelSubtitle: {
      margin: '0.35rem 0 1rem',
      color: '#64748b',
      fontSize: '0.84rem',
      lineHeight: 1.5,
    },
  };

  return (
    <div style={styles.container}>
      <div style={styles.shell}>
        <div style={styles.header}>
          <div>
            <h1 style={styles.title}>Super User Dashboard</h1>
            <p style={styles.subtitle}>
              Portfolio view across tenants, workflows, incident load, and knowledge base quality. Range filtered to {analytics.rangeLabel}.
            </p>
          </div>
          <DateRangeSelector
            value={dateRange}
            onChange={setDateRange}
            customStart={customStartDate}
            customEnd={customEndDate}
            onCustomStartChange={setCustomStartDate}
            onCustomEndChange={setCustomEndDate}
          />
        </div>

        <div style={styles.statGrid}>
          {[
            { label: 'Tenants in View', value: analytics.totalTenants, tone: '#2563eb' },
            { label: 'Active Tenants', value: analytics.activeTenants, tone: '#1d4ed8' },
            { label: 'Workflow Versions', value: analytics.totalWorkflows, tone: '#047857' },
            { label: 'Workflow Use Cases', value: analytics.workflowUseCases, tone: '#0f766e' },
            { label: 'Incident Volume', value: analytics.incidentVolume, tone: '#b45309' },
            { label: 'KB Patterns', value: analytics.kbTrue + analytics.kbFalse, tone: '#7c3aed' },
          ].map((card) => (
            <div key={card.label} style={styles.statCard}>
              <div style={{ ...styles.statValue, color: card.tone }}>{card.value}</div>
              <div style={styles.statLabel}>{card.label}</div>
            </div>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1.05fr 0.95fr', gap: '1rem', marginBottom: '1rem' }}>
          <section style={styles.panel}>
            <h2 style={styles.panelTitle}>Knowledge Base Balance</h2>
            <p style={styles.panelSubtitle}>
              Global pattern mix and movement across the selected window, with week-over-week direction built from dated KB entries.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: '14px', alignItems: 'center' }}>
              <DonutChart
                segments={analytics.kbDonutSegments}
                centerLabel="KB Patterns"
                centerValue={analytics.kbTrue + analytics.kbFalse}
              />
              <div style={{ display: 'grid', gap: '10px' }}>
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <TrendBadge delta={analytics.trueTrendDelta} label="true" />
                  <TrendBadge delta={analytics.falseTrendDelta} label="false" />
                </div>
                {analytics.kbDonutSegments.map((segment) => (
                  <div key={segment.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ width: 11, height: 11, borderRadius: '999px', background: segment.color, display: 'inline-block' }} />
                      <span style={{ color: '#0f172a', fontSize: '0.84rem', fontWeight: 700 }}>{segment.label}</span>
                    </div>
                    <span style={{ color: '#475569', fontSize: '0.82rem', fontWeight: 800 }}>{segment.value}</span>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ marginTop: '14px' }}>
              <LineTrendChart labels={analytics.kbLine.labels} series={analytics.kbLine.series} />
            </div>
          </section>

          <section style={styles.panel}>
            <h2 style={styles.panelTitle}>Tenant Load Bubble Map</h2>
            <p style={styles.panelSubtitle}>
              Each bubble is a tenant. Size reflects incident volume, X shows workflow count, and Y shows the false KB ratio.
            </p>
            <BubbleChart points={analytics.bubblePoints} />
          </section>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '0.95fr 1.05fr', gap: '1rem' }}>
          <section style={styles.panel}>
            <h2 style={styles.panelTitle}>Platform Coverage</h2>
            <p style={styles.panelSubtitle}>
              Snapshot of how tenant activation, workflow rollout, and incident concentration line up in the selected view.
            </p>
            <div style={{ display: 'grid', gap: '12px' }}>
              {[
                {
                  label: 'Active Tenant Footprint',
                  value: analytics.activeTenants,
                  total: analytics.totalTenants,
                  color: '#2563eb',
                },
                {
                  label: 'Workflow Reach',
                  value: analytics.totalWorkflows,
                  total: Math.max(analytics.totalTenants, analytics.totalWorkflows || 1),
                  color: '#047857',
                },
                {
                  label: 'KB True Share',
                  value: analytics.kbTrue,
                  total: analytics.kbTrue + analytics.kbFalse,
                  color: '#10b981',
                },
                {
                  label: 'KB False Share',
                  value: analytics.kbFalse,
                  total: analytics.kbTrue + analytics.kbFalse,
                  color: '#ef4444',
                },
              ].map((item) => (
                <div key={item.label}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '10px', marginBottom: '4px' }}>
                    <div style={{ color: '#0f172a', fontSize: '0.84rem', fontWeight: 800 }}>{item.label}</div>
                    <div style={{ color: '#475569', fontSize: '0.8rem', fontWeight: 700 }}>
                      {item.value}/{item.total || 0}
                    </div>
                  </div>
                  <div style={{ height: '10px', borderRadius: '999px', background: '#e2e8f0', overflow: 'hidden' }}>
                    <div style={{ width: `${getRatio(item.value, item.total || 0)}%`, height: '100%', borderRadius: '999px', background: `linear-gradient(90deg, ${item.color}, ${item.color}bb)` }} />
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section style={styles.panel}>
            <h2 style={styles.panelTitle}>Workflow Portfolio Leaderboard</h2>
            <p style={styles.panelSubtitle}>
              Version-level snapshot ranked by workflow complexity. Includes the tenant load and false KB pressure around each deployment.
            </p>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    {['Tenant', 'Use Case', 'Version', 'Nodes', 'Incident Volume', 'False KB Ratio'].map((label) => (
                      <th key={label} style={{ textAlign: 'left', padding: '10px 12px', fontSize: '0.76rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {analytics.leaderboard.map((workflow) => (
                    <tr key={`${workflow.workflow_id}-${workflow.version}`} style={{ borderTop: '1px solid #e2e8f0' }}>
                      <td style={{ padding: '11px 12px', fontSize: '0.83rem', fontWeight: 800, color: '#0f172a' }}>{workflow.tenant_name}</td>
                      <td style={{ padding: '11px 12px', fontSize: '0.82rem', color: '#334155' }}>{workflow.use_case}</td>
                      <td style={{ padding: '11px 12px', fontSize: '0.82rem', color: '#334155' }}>v{workflow.version}</td>
                      <td style={{ padding: '11px 12px', fontSize: '0.82rem', color: '#334155' }}>{workflow.nodes}</td>
                      <td style={{ padding: '11px 12px', fontSize: '0.82rem', color: '#334155' }}>{workflow.incident_volume}</td>
                      <td style={{ padding: '11px 12px', fontSize: '0.82rem', color: '#334155' }}>{workflow.false_ratio}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default SuperUserDashboard;
