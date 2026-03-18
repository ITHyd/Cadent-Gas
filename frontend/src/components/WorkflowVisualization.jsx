import { useEffect, useState } from 'react';
import mermaid from 'mermaid';
import { API_BASE_URL, authFetch } from '../services/api';

const WorkflowVisualization = ({ workflowId, currentStep }) => {
  const [mermaidDiagram, setMermaidDiagram] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    mermaid.initialize({ startOnLoad: false, theme: 'neutral' });
  }, []);

  useEffect(() => {
    const fetchWorkflowDiagram = async () => {
      if (!workflowId) {
        setMermaidDiagram('');
        setError('No workflow selected yet.');
        return;
      }

      setIsLoading(true);
      setError('');

      try {
        const response = await authFetch(`${API_BASE_URL}/api/v1/workflows/${workflowId}/mermaid`);
        if (!response.ok) {
          throw new Error('Failed to fetch workflow diagram');
        }
        const data = await response.json();
        setMermaidDiagram(data.mermaid || '');
      } catch {
        setError('Workflow diagram unavailable.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchWorkflowDiagram();
  }, [workflowId]);

  useEffect(() => {
    if (mermaidDiagram) {
      mermaid.run({ querySelector: '.mermaid' });
    }
  }, [mermaidDiagram]);

  return (
    <div className="p-6">
      <h2 className="text-xl font-bold text-slate-900">Workflow Progress</h2>

      {currentStep && (
        <div className="mb-4 mt-4 rounded-xl border border-brand-200 bg-brand-50 p-3">
          <p className="text-sm font-medium text-brand-900">
            Current Step: <span className="font-bold capitalize">{currentStep}</span>
          </p>
        </div>
      )}

      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
        {isLoading && <div className="py-8 text-center text-sm text-slate-500">Loading workflow diagram...</div>}
        {!isLoading && error && <div className="py-8 text-center text-sm text-slate-500">{error}</div>}
        {!isLoading && !error && mermaidDiagram ? (
          <div className="mermaid">{mermaidDiagram}</div>
        ) : (
          !isLoading && !error && <div className="py-8 text-center text-sm text-slate-500">No diagram available.</div>
        )}
      </div>

      <div className="mt-6 space-y-3">
        <h3 className="text-sm font-semibold text-slate-700">Legend</h3>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded bg-blue-500" />
            <span className="text-slate-600">Question/Input</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded bg-amber-500" />
            <span className="text-slate-600">Processing/Analysis</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded bg-emerald-500" />
            <span className="text-slate-600">Decision Point</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded bg-red-500" />
            <span className="text-slate-600">Emergency Override</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default WorkflowVisualization;
