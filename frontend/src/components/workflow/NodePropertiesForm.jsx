import { useState, useEffect, useMemo } from 'react';
import CustomSelect from '../CustomSelect';

const OPERATIONS = [
  { value: 'add', label: '+  Add', symbol: '+', description: 'Sum values together' },
  { value: 'subtract', label: '−  Subtract', symbol: '−', description: 'Subtract from base' },
  { value: 'multiply', label: '×  Multiply', symbol: '×', description: 'Multiply values' },
  { value: 'divide', label: '÷  Divide', symbol: '÷', description: 'Divide values' },
  { value: 'min', label: 'Min', symbol: 'min', description: 'Take minimum' },
  { value: 'max', label: 'Max', symbol: 'max', description: 'Take maximum' },
  { value: 'average', label: 'Avg', symbol: 'avg', description: 'Average of values' },
  { value: 'custom', label: 'Custom', symbol: 'f(x)', description: 'Custom expression' },
];

const OP_SYMBOLS = { add: '+', subtract: '−', multiply: '×', divide: '÷', min: 'min()', max: 'max()', average: 'avg()' };

/**
 * Parse a calculation string to extract structured terms.
 * e.g. "risk_score = min(total_score, 100)" → { operation: 'min', terms: [{variable:'total_score'}, {constant:100}], resultVar: 'risk_score' }
 */
const parseCalculation = (calc) => {
  if (!calc) return null;
  const trimmed = calc.trim();

  // Try "result_var = expression"
  const eqIdx = trimmed.indexOf('=');
  if (eqIdx < 0) return null;

  const lhs = trimmed.slice(0, eqIdx).trim();
  const rhs = trimmed.slice(eqIdx + 1).trim();

  // Detect min/max wrapping
  const minMatch = rhs.match(/^min\((.+)\)$/);
  const maxMatch = rhs.match(/^max\((.+)\)$/);

  if (minMatch) {
    const args = minMatch[1].split(',').map(a => a.trim());
    return { resultVar: lhs, operation: 'min', terms: args.map(parseTerm) };
  }
  if (maxMatch) {
    const args = maxMatch[1].split(',').map(a => a.trim());
    return { resultVar: lhs, operation: 'max', terms: args.map(parseTerm) };
  }

  // Detect simple binary: a + b, a * b, etc.
  for (const [op, regex] of [
    ['multiply', /^(.+?)\s*\*\s*(.+)$/],
    ['divide', /^(.+?)\s*\/\s*(.+)$/],
    ['add', /^(.+?)\s*\+\s*(.+)$/],
    ['subtract', /^(.+?)\s*-\s*(.+)$/],
  ]) {
    const m = rhs.match(regex);
    if (m) {
      return { resultVar: lhs, operation: op, terms: [parseTerm(m[1].trim()), parseTerm(m[2].trim())] };
    }
  }

  // Single variable assignment
  return { resultVar: lhs, operation: 'add', terms: [parseTerm(rhs)] };
};

const parseTerm = (str) => {
  const n = Number(str);
  if (!isNaN(n) && str !== '') return { type: 'constant', value: n };
  return { type: 'variable', value: str };
};

/**
 * Build a calculation string from structured terms.
 */
const buildCalculation = (resultVar, operation, terms) => {
  if (!resultVar || terms.length === 0) return '';

  const termStrs = terms.map(t => t.type === 'constant' ? String(t.value) : t.value).filter(Boolean);
  if (termStrs.length === 0) return '';

  switch (operation) {
    case 'min': return `${resultVar} = min(${termStrs.join(', ')})`;
    case 'max': return `${resultVar} = max(${termStrs.join(', ')})`;
    case 'average': return `${resultVar} = (${termStrs.join(' + ')}) / ${termStrs.length}`;
    case 'add': return `${resultVar} = ${termStrs.join(' + ')}`;
    case 'subtract': return `${resultVar} = ${termStrs.join(' - ')}`;
    case 'multiply': return `${resultVar} = ${termStrs.join(' * ')}`;
    case 'divide': return `${resultVar} = ${termStrs.join(' / ')}`;
    case 'custom': return `${resultVar} = ${termStrs[0] || ''}`;
    default: return `${resultVar} = ${termStrs.join(' + ')}`;
  }
};

const NodePropertiesForm = ({ node, onChange, onDelete, allNodes = [] }) => {
  const [data, setData] = useState(node?.data || {});

  useEffect(() => {
    setData(node?.data || {});
  }, [node]);

  /* ── Scored questions discovery (used by CALCULATE form) ── */
  const scoredQuestionNodes = useMemo(() => {
    return allNodes
      .filter(n => {
        if (n.type !== 'QUESTION') return false;
        const opts = n.data?.options || [];
        return opts.some(o => typeof o === 'object' && o !== null && o.score !== undefined && o.score !== '');
      })
      .map(n => {
        const opts = n.data.options.filter(o => typeof o === 'object' && o !== null);
        const scores = opts.map(o => Number(o.score) || 0);
        const minScore = Math.min(...scores);
        const maxScore = Math.max(...scores);
        return {
          nodeId: n.id,
          variable: n.data.variable || n.id,
          question: n.data.question || n.id,
          options: opts,
          minScore,
          maxScore,
          scoreVar: `${n.data.variable || n.id}_score`,
        };
      });
  }, [allNodes]);

  if (!node) {
    return (
      <div style={{ padding: '16px', color: '#6b7280', textAlign: 'center' }}>
        <p>Select a node to edit its properties</p>
      </div>
    );
  }

  const handleChange = (field, value) => {
    const updated = { ...data, [field]: value };
    setData(updated);
    onChange(updated);
  };

  const styles = {
    formGroup: { marginBottom: '16px' },
    label: { display: 'block', marginBottom: '6px', fontWeight: '600', color: '#374151', fontSize: '13px' },
    input: { width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box' },
    textarea: { width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box', fontFamily: 'inherit', resize: 'vertical' },
    select: { width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '14px', boxSizing: 'border-box' },
    deleteButton: { width: '100%', padding: '10px', backgroundColor: '#ef4444', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: '600', marginTop: '24px' },
    helpText: { fontSize: '12px', color: '#6b7280', marginTop: '4px' },
  };

  /* ═══════════════ QUESTION FORM ═══════════════ */
  const renderQuestionForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Question Text</label>
        <textarea
          style={styles.textarea}
          value={data.question || ''}
          onChange={(e) => handleChange('question', e.target.value)}
          rows={4}
          placeholder="What is your question?"
        />
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Variable Name</label>
        <input
          type="text"
          style={styles.input}
          value={data.variable || ''}
          onChange={(e) => handleChange('variable', e.target.value)}
          placeholder="smell_intensity"
        />
        <div style={styles.helpText}>Variable to store the answer</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Options</label>
        {(data.options || []).map((opt, index) => {
          const isScored = typeof opt === 'object' && opt !== null && opt.label !== undefined;
          const label = isScored ? opt.label : (typeof opt === 'string' ? opt : '');
          const score = isScored ? opt.score : '';
          const operation = isScored ? (opt.operation || 'add') : 'add';
          const hasScore = score !== '' && score !== undefined;

          return (
            <div key={index} style={{
              marginBottom: '8px',
              padding: '8px 10px',
              backgroundColor: hasScore ? '#faf5ff' : '#f9fafb',
              border: `1px solid ${hasScore ? '#e9d5ff' : '#e5e7eb'}`,
              borderRadius: '8px',
              transition: 'all 0.15s',
            }}>
              <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                <input
                  type="text"
                  style={{ ...styles.input, flex: 2, fontSize: '13px', padding: '6px 10px' }}
                  value={label}
                  placeholder="Option label"
                  onChange={(e) => {
                    const updated = [...(data.options || [])];
                    if (hasScore) {
                      updated[index] = { label: e.target.value, score: Number(score) || 0, operation };
                    } else {
                      updated[index] = e.target.value;
                    }
                    handleChange('options', updated);
                  }}
                />
                <button
                  onClick={() => {
                    const updated = (data.options || []).filter((_, i) => i !== index);
                    handleChange('options', updated);
                  }}
                  style={{ padding: '4px 8px', cursor: 'pointer', color: '#ef4444', background: 'none', border: '1px solid #e5e7eb', borderRadius: '4px', fontSize: '12px', flexShrink: 0 }}
                >
                  X
                </button>
              </div>

              {/* Score row */}
              <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginTop: '6px' }}>
                {/* Operation selector */}
                <select
                  value={operation}
                  onChange={(e) => {
                    const updated = [...(data.options || [])];
                    const val = e.target.value;
                    updated[index] = { label: label || '', score: Number(score) || 0, operation: val };
                    handleChange('options', updated);
                  }}
                  style={{
                    padding: '4px 6px', border: '1px solid #d1d5db', borderRadius: '4px',
                    fontSize: '12px', backgroundColor: '#fff', cursor: 'pointer', width: '56px', flexShrink: 0,
                    color: hasScore ? '#7c3aed' : '#9ca3af',
                  }}
                >
                  <option value="add">+</option>
                  <option value="subtract">−</option>
                  <option value="multiply">×</option>
                </select>
                <input
                  type="number"
                  style={{
                    ...styles.input, flex: 1, maxWidth: '72px', fontSize: '13px', padding: '4px 8px',
                    fontWeight: hasScore ? '600' : '400',
                    color: hasScore ? '#7c3aed' : '#374151',
                    borderColor: hasScore ? '#c4b5fd' : '#d1d5db',
                  }}
                  value={score !== undefined && score !== '' ? score : ''}
                  placeholder="Score"
                  onChange={(e) => {
                    const updated = [...(data.options || [])];
                    const val = e.target.value;
                    if (val === '') {
                      updated[index] = label;
                    } else {
                      updated[index] = { label: label || '', score: Number(val) || 0, operation };
                    }
                    handleChange('options', updated);
                  }}
                />
                {hasScore && (
                  <div style={{
                    fontSize: '11px', color: '#7c3aed', fontWeight: '600', whiteSpace: 'nowrap',
                    padding: '2px 6px', backgroundColor: '#ede9fe', borderRadius: '4px',
                  }}>
                    {operation === 'add' ? '+' : operation === 'subtract' ? '−' : '×'}{score} pts
                  </div>
                )}
              </div>
            </div>
          );
        })}
        <button
          onClick={() => handleChange('options', [...(data.options || []), ''])}
          style={{ marginTop: '4px', fontSize: '13px', color: '#3b82f6', cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
        >
          + Add Option
        </button>
        <div style={styles.helpText}>
          Set a score value and operation (+, −, ×) for risk accumulation. Leave score empty for plain options.
        </div>

        {/* Score summary for this question */}
        {(() => {
          const opts = (data.options || []).filter(o => typeof o === 'object' && o !== null && o.score !== undefined && o.score !== '');
          if (opts.length === 0) return null;
          const scores = opts.map(o => Number(o.score) || 0);
          return (
            <div style={{
              marginTop: '10px', padding: '10px 12px',
              background: 'linear-gradient(135deg, #faf5ff 0%, #ede9fe 100%)',
              borderRadius: '8px', border: '1px solid #ddd6fe',
            }}>
              <div style={{ fontSize: '11px', fontWeight: '700', color: '#6d28d9', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Score Range for this Question
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ flex: 1, height: '6px', backgroundColor: '#e9d5ff', borderRadius: '3px', position: 'relative', overflow: 'hidden' }}>
                  <div style={{
                    position: 'absolute', left: `${Math.min(...scores)}%`, right: `${100 - Math.max(...scores)}%`,
                    height: '100%', backgroundColor: '#8b5cf6', borderRadius: '3px', minWidth: '4px',
                  }} />
                </div>
                <span style={{ fontSize: '12px', fontWeight: '600', color: '#7c3aed', whiteSpace: 'nowrap' }}>
                  {Math.min(...scores)} – {Math.max(...scores)} pts
                </span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '6px' }}>
                {opts.map((o, i) => (
                  <span key={i} style={{
                    fontSize: '10px', padding: '2px 6px', borderRadius: '4px',
                    backgroundColor: '#fff', border: '1px solid #ddd6fe', color: '#5b21b6',
                  }}>
                    {o.label}: {o.operation === 'subtract' ? '−' : o.operation === 'multiply' ? '×' : '+'}{o.score}
                  </span>
                ))}
              </div>
            </div>
          );
        })()}
      </div>
    </>
  );

  /* ═══════════════ CALCULATE FORM (Enhanced) ═══════════════ */
  const renderCalculateForm = () => {
    const parsed = parseCalculation(data.calculation);
    const resultVar = data.result_variable || parsed?.resultVar || 'risk_score';

    // Structured terms state
    const [calcMode, setCalcMode] = useState(data._calc_mode || (parsed ? 'visual' : (data.calculation ? 'custom' : 'visual')));
    const [operation, setOperation] = useState(
      data._calc_operation || parsed?.operation || 'min'
    );
    const [terms, setTerms] = useState(
      data._calc_terms || parsed?.terms || [{ type: 'variable', value: 'total_score' }, { type: 'constant', value: 100 }]
    );

    const updateCalc = (newOp, newTerms, newResultVar) => {
      const op = newOp ?? operation;
      const t = newTerms ?? terms;
      const rv = newResultVar ?? resultVar;
      const calc = buildCalculation(rv, op, t);
      const updated = {
        ...data,
        calculation: calc,
        result_variable: rv,
        _calc_mode: calcMode,
        _calc_operation: op,
        _calc_terms: t,
      };
      setData(updated);
      onChange(updated);
    };

    const addTerm = () => {
      const newTerms = [...terms, { type: 'variable', value: '' }];
      setTerms(newTerms);
      updateCalc(operation, newTerms, resultVar);
    };

    const removeTerm = (idx) => {
      const newTerms = terms.filter((_, i) => i !== idx);
      setTerms(newTerms);
      updateCalc(operation, newTerms, resultVar);
    };

    const updateTerm = (idx, field, value) => {
      const newTerms = [...terms];
      if (field === 'type') {
        newTerms[idx] = { type: value, value: value === 'constant' ? 0 : '' };
      } else {
        newTerms[idx] = { ...newTerms[idx], [field]: value };
      }
      setTerms(newTerms);
      updateCalc(operation, newTerms, resultVar);
    };

    // Available variables from question nodes
    const availableVars = useMemo(() => {
      const vars = [{ value: 'total_score', label: 'total_score (accumulated)' }];
      allNodes.forEach(n => {
        if (n.type !== 'QUESTION') return;
        const v = n.data?.variable || n.id;
        vars.push({ value: v, label: v });
        const opts = n.data?.options || [];
        if (opts.some(o => typeof o === 'object' && o !== null && o.score !== undefined)) {
          vars.push({ value: `${v}_score`, label: `${v}_score (points)` });
        }
      });
      return vars;
    }, [allNodes]);

    // Live formula preview
    const formulaPreview = buildCalculation(resultVar, operation, terms);

    return (
      <>
        {/* Score Inputs Breakdown */}
        {scoredQuestionNodes.length > 0 && (
          <div style={styles.formGroup}>
            <label style={styles.label}>Score Inputs from Questions</label>
            <div style={{
              padding: '10px', backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0',
              borderRadius: '8px', maxHeight: '200px', overflowY: 'auto',
            }}>
              {scoredQuestionNodes.map((sq, idx) => (
                <div key={sq.nodeId} style={{
                  padding: '8px 10px', marginBottom: idx < scoredQuestionNodes.length - 1 ? '6px' : 0,
                  backgroundColor: '#fff', borderRadius: '6px', border: '1px solid #dcfce7',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <span style={{ fontSize: '12px', fontWeight: '600', color: '#166534' }}>
                      {sq.question.length > 35 ? sq.question.slice(0, 35) + '...' : sq.question}
                    </span>
                    <span style={{
                      fontSize: '11px', fontWeight: '700', color: '#15803d',
                      padding: '1px 6px', backgroundColor: '#dcfce7', borderRadius: '4px',
                    }}>
                      {sq.minScore}–{sq.maxScore} pts
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px' }}>
                    {sq.options.map((o, i) => (
                      <span key={i} style={{
                        fontSize: '10px', padding: '1px 5px', borderRadius: '3px',
                        backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', color: '#15803d',
                      }}>
                        {o.label}: {o.operation === 'subtract' ? '−' : o.operation === 'multiply' ? '×' : '+'}{o.score}
                      </span>
                    ))}
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280', marginTop: '3px', fontFamily: 'monospace' }}>
                    var: {sq.scoreVar}
                  </div>
                </div>
              ))}
              {/* Total range */}
              <div style={{
                marginTop: '8px', padding: '8px 10px',
                background: 'linear-gradient(135deg, #dcfce7, #bbf7d0)',
                borderRadius: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <span style={{ fontSize: '12px', fontWeight: '700', color: '#14532d' }}>
                  total_score range
                </span>
                <span style={{ fontSize: '12px', fontWeight: '700', color: '#166534' }}>
                  {scoredQuestionNodes.reduce((s, q) => s + q.minScore, 0)} – {scoredQuestionNodes.reduce((s, q) => s + q.maxScore, 0)} pts
                </span>
              </div>
            </div>
            <div style={styles.helpText}>
              These question nodes contribute scored options that auto-accumulate into <code>total_score</code>
            </div>
          </div>
        )}

        {/* Mode Toggle */}
        <div style={styles.formGroup}>
          <div style={{ display: 'flex', gap: '4px', padding: '3px', backgroundColor: '#f3f4f6', borderRadius: '8px' }}>
            <button
              onClick={() => { setCalcMode('visual'); }}
              style={{
                flex: 1, padding: '6px 8px', border: 'none', borderRadius: '6px', cursor: 'pointer',
                fontSize: '12px', fontWeight: '600', transition: 'all 0.15s',
                backgroundColor: calcMode === 'visual' ? '#fff' : 'transparent',
                color: calcMode === 'visual' ? '#7c3aed' : '#6b7280',
                boxShadow: calcMode === 'visual' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              Visual Builder
            </button>
            <button
              onClick={() => { setCalcMode('custom'); }}
              style={{
                flex: 1, padding: '6px 8px', border: 'none', borderRadius: '6px', cursor: 'pointer',
                fontSize: '12px', fontWeight: '600', transition: 'all 0.15s',
                backgroundColor: calcMode === 'custom' ? '#fff' : 'transparent',
                color: calcMode === 'custom' ? '#7c3aed' : '#6b7280',
                boxShadow: calcMode === 'custom' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              Custom Expression
            </button>
          </div>
        </div>

        {calcMode === 'visual' ? (
          <>
            {/* Result variable */}
            <div style={styles.formGroup}>
              <label style={styles.label}>Result Variable</label>
              <input
                type="text"
                style={styles.input}
                value={resultVar}
                onChange={(e) => {
                  updateCalc(operation, terms, e.target.value);
                }}
                placeholder="risk_score"
              />
              <div style={styles.helpText}>Variable to store the calculated result</div>
            </div>

            {/* Operation */}
            <div style={styles.formGroup}>
              <label style={styles.label}>Operation</label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '4px' }}>
                {OPERATIONS.filter(o => o.value !== 'custom').map(op => (
                  <button
                    key={op.value}
                    onClick={() => {
                      setOperation(op.value);
                      updateCalc(op.value, terms, resultVar);
                    }}
                    title={op.description}
                    style={{
                      padding: '8px 4px', border: `1.5px solid ${operation === op.value ? '#8b5cf6' : '#e5e7eb'}`,
                      borderRadius: '6px', cursor: 'pointer', fontSize: '12px', fontWeight: '600',
                      backgroundColor: operation === op.value ? '#ede9fe' : '#fff',
                      color: operation === op.value ? '#7c3aed' : '#374151',
                      transition: 'all 0.15s', textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '16px', marginBottom: '2px' }}>{op.symbol}</div>
                    <div style={{ fontSize: '10px', color: '#6b7280' }}>{op.label.split('  ')[1] || op.label}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Terms */}
            <div style={styles.formGroup}>
              <label style={styles.label}>Values</label>
              {terms.map((term, idx) => (
                <div key={idx} style={{
                  display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '6px',
                  padding: '8px', backgroundColor: '#faf5ff', border: '1px solid #e9d5ff', borderRadius: '6px',
                }}>
                  {/* Operator symbol between terms */}
                  {idx > 0 && (
                    <div style={{
                      width: '24px', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      backgroundColor: '#8b5cf6', color: '#fff', borderRadius: '4px', fontSize: '14px', fontWeight: '700', flexShrink: 0,
                    }}>
                      {['min', 'max', 'average'].includes(operation)
                        ? ','
                        : OP_SYMBOLS[operation] || '+'}
                    </div>
                  )}
                  {idx === 0 && terms.length > 1 && (
                    <div style={{ width: '24px', flexShrink: 0 }} />
                  )}

                  {/* Type toggle */}
                  <select
                    value={term.type}
                    onChange={(e) => updateTerm(idx, 'type', e.target.value)}
                    style={{
                      padding: '4px 4px', border: '1px solid #d1d5db', borderRadius: '4px',
                      fontSize: '11px', backgroundColor: '#fff', cursor: 'pointer', width: '46px', flexShrink: 0,
                    }}
                  >
                    <option value="variable">Var</option>
                    <option value="constant">Num</option>
                  </select>

                  {/* Value input */}
                  {term.type === 'variable' ? (
                    <select
                      value={term.value}
                      onChange={(e) => updateTerm(idx, 'value', e.target.value)}
                      style={{
                        flex: 1, padding: '6px 8px', border: '1px solid #c4b5fd', borderRadius: '4px',
                        fontSize: '12px', backgroundColor: '#fff', cursor: 'pointer',
                      }}
                    >
                      <option value="">Select variable...</option>
                      {availableVars.map(v => (
                        <option key={v.value} value={v.value}>{v.label}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="number"
                      value={term.value}
                      onChange={(e) => updateTerm(idx, 'value', e.target.value === '' ? 0 : Number(e.target.value))}
                      style={{
                        flex: 1, padding: '6px 8px', border: '1px solid #c4b5fd', borderRadius: '4px',
                        fontSize: '13px', fontWeight: '600', color: '#7c3aed',
                      }}
                      placeholder="0"
                    />
                  )}

                  {/* Remove term */}
                  {terms.length > 1 && (
                    <button
                      onClick={() => removeTerm(idx)}
                      style={{
                        padding: '2px 6px', cursor: 'pointer', color: '#ef4444', background: 'none',
                        border: '1px solid #fecaca', borderRadius: '4px', fontSize: '11px', flexShrink: 0,
                      }}
                    >
                      X
                    </button>
                  )}
                </div>
              ))}
              <button
                onClick={addTerm}
                style={{ marginTop: '4px', fontSize: '12px', color: '#7c3aed', cursor: 'pointer', background: 'none', border: 'none', padding: 0, fontWeight: '600' }}
              >
                + Add Value
              </button>
            </div>

            {/* Live Formula Preview */}
            <div style={{
              padding: '12px', borderRadius: '8px',
              background: 'linear-gradient(135deg, #faf5ff, #ede9fe)',
              border: '1px solid #ddd6fe', marginBottom: '16px',
            }}>
              <div style={{ fontSize: '10px', fontWeight: '700', color: '#7c3aed', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Generated Formula
              </div>
              <code style={{
                display: 'block', fontSize: '13px', fontFamily: 'monospace', color: '#5b21b6',
                padding: '8px 10px', backgroundColor: '#fff', borderRadius: '4px', border: '1px solid #e9d5ff',
                wordBreak: 'break-all',
              }}>
                {formulaPreview || 'No formula yet'}
              </code>

              {/* Visual math breakdown */}
              {terms.length > 0 && (
                <div style={{ marginTop: '8px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px' }}>
                  <span style={{ fontSize: '12px', fontWeight: '600', color: '#7c3aed' }}>{resultVar} =</span>
                  {['min', 'max', 'average'].includes(operation) && (
                    <span style={{ fontSize: '12px', fontWeight: '600', color: '#8b5cf6' }}>{operation}(</span>
                  )}
                  {terms.map((t, i) => (
                    <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      {i > 0 && !['min', 'max', 'average'].includes(operation) && (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          width: '18px', height: '18px', borderRadius: '3px',
                          backgroundColor: '#8b5cf6', color: '#fff', fontSize: '12px', fontWeight: '700',
                        }}>
                          {OP_SYMBOLS[operation] || '+'}
                        </span>
                      )}
                      {i > 0 && ['min', 'max', 'average'].includes(operation) && (
                        <span style={{ color: '#8b5cf6', fontWeight: '600' }}>,</span>
                      )}
                      <span style={{
                        padding: '2px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: '600',
                        backgroundColor: t.type === 'variable' ? '#dbeafe' : '#fef3c7',
                        color: t.type === 'variable' ? '#1d4ed8' : '#92400e',
                        border: `1px solid ${t.type === 'variable' ? '#bfdbfe' : '#fde68a'}`,
                      }}>
                        {t.type === 'constant' ? t.value : (t.value || '?')}
                      </span>
                    </span>
                  ))}
                  {['min', 'max', 'average'].includes(operation) && (
                    <span style={{ fontSize: '12px', fontWeight: '600', color: '#8b5cf6' }}>)</span>
                  )}
                </div>
              )}
            </div>

            {/* Example scores */}
            {scoredQuestionNodes.length > 0 && (
              <div style={{
                padding: '10px 12px', borderRadius: '8px',
                backgroundColor: '#fffbeb', border: '1px solid #fde68a', marginBottom: '16px',
              }}>
                <div style={{ fontSize: '10px', fontWeight: '700', color: '#92400e', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Example Calculation
                </div>
                <div style={{ fontSize: '12px', color: '#78350f', lineHeight: '1.6' }}>
                  {(() => {
                    const minTotal = scoredQuestionNodes.reduce((s, q) => s + q.minScore, 0);
                    const maxTotal = scoredQuestionNodes.reduce((s, q) => s + q.maxScore, 0);
                    const cap = terms.find(t => t.type === 'constant')?.value;

                    if (operation === 'min' && cap !== undefined) {
                      return (
                        <>
                          <div>If user picks lowest options: total_score = <strong>{minTotal}</strong></div>
                          <div style={{ marginLeft: '8px', fontFamily: 'monospace', fontSize: '11px' }}>
                            {resultVar} = min({minTotal}, {cap}) = <strong>{Math.min(minTotal, cap)}</strong>
                          </div>
                          <div style={{ marginTop: '4px' }}>If user picks highest options: total_score = <strong>{maxTotal}</strong></div>
                          <div style={{ marginLeft: '8px', fontFamily: 'monospace', fontSize: '11px' }}>
                            {resultVar} = min({maxTotal}, {cap}) = <strong>{Math.min(maxTotal, cap)}</strong>
                          </div>
                        </>
                      );
                    }
                    return (
                      <>
                        <div>Range: total_score = <strong>{minTotal}</strong> to <strong>{maxTotal}</strong></div>
                        <div style={{ marginTop: '2px', fontFamily: 'monospace', fontSize: '11px' }}>
                          {resultVar} = {operation}({minTotal}...{maxTotal})
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>
            )}
          </>
        ) : (
          /* Custom expression mode */
          <>
            <div style={styles.formGroup}>
              <label style={styles.label}>Calculation Expression</label>
              <textarea
                style={{ ...styles.textarea, fontFamily: 'monospace' }}
                value={data.calculation || ''}
                onChange={(e) => handleChange('calculation', e.target.value)}
                rows={4}
                placeholder="risk_score = min(total_score, 100)"
              />
              <div style={styles.helpText}>Python expression. Available: min, max, abs, int, float, round, len, sum</div>
            </div>

            <div style={styles.formGroup}>
              <label style={styles.label}>Result Variable</label>
              <input
                type="text"
                style={styles.input}
                value={data.result_variable || ''}
                onChange={(e) => handleChange('result_variable', e.target.value)}
                placeholder="risk_score"
              />
              <div style={styles.helpText}>Variable to store the result</div>
            </div>

            {/* Available variables reference */}
            {availableVars.length > 0 && (
              <div style={{
                padding: '10px 12px', borderRadius: '8px',
                backgroundColor: '#f0f9ff', border: '1px solid #bae6fd',
              }}>
                <div style={{ fontSize: '10px', fontWeight: '700', color: '#0369a1', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Available Variables
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                  {availableVars.map(v => (
                    <code key={v.value} style={{
                      fontSize: '11px', padding: '2px 6px', borderRadius: '4px',
                      backgroundColor: 'rgba(141, 233, 113, 0.15)', color: '#030304', cursor: 'pointer',
                    }}
                      onClick={() => {
                        const current = data.calculation || '';
                        handleChange('calculation', current + v.value);
                      }}
                      title="Click to insert"
                    >
                      {v.value}
                    </code>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </>
    );
  };

  /* ═══════════════ OTHER FORMS (unchanged) ═══════════════ */

  const renderConditionForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Expression</label>
        <textarea
          style={styles.textarea}
          value={data.expression || ''}
          onChange={(e) => handleChange('expression', e.target.value)}
          rows={4}
          placeholder="smell_intensity == 'strong'"
        />
        <div style={styles.helpText}>
          Python expression that evaluates to True/False
        </div>
      </div>

      <div style={{ ...styles.formGroup, marginTop: '20px' }}>
        <div style={{ fontSize: '13px', color: '#6b7280', lineHeight: '1.5' }}>
          <strong>Available variables:</strong> All variables collected from previous
          QUESTION nodes
          <br />
          <br />
          <strong>Examples:</strong>
          <br />&#x2022; smell_intensity == 'strong'
          <br />&#x2022; has_symptoms == 'yes'
          <br />&#x2022; smell_intensity in ['strong', 'overwhelming']
        </div>
      </div>
    </>
  );

  const renderDecisionForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Outcome</label>
        <CustomSelect
          value={data.outcome || ''}
          onChange={(v) => handleChange('outcome', v)}
          placeholder="Select outcome"
          options={[
            { value: 'emergency_dispatch', label: '🚨 Emergency Dispatch' },
            { value: 'schedule_engineer', label: '📅 Schedule Engineer' },
            { value: 'monitor', label: '👁️ Monitor' },
            { value: 'close_with_guidance', label: '✅ Close with Guidance' },
          ]}
        />
        <div style={styles.helpText}>Final decision for this workflow path</div>
      </div>

      <div style={{ ...styles.formGroup, marginTop: '20px' }}>
        <div
          style={{
            padding: '12px',
            backgroundColor: '#fef3c7',
            borderRadius: '6px',
            fontSize: '13px',
            color: '#92400e',
          }}
        >
          DECISION nodes end the workflow. No outgoing connections needed.
        </div>
      </div>
    </>
  );

  const renderMLModelForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Model Name</label>
        <input
          type="text"
          style={styles.input}
          value={data.model_name || ''}
          onChange={(e) => handleChange('model_name', e.target.value)}
          placeholder="risk_classifier"
        />
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Input Variables (comma-separated)</label>
        <input
          type="text"
          style={styles.input}
          value={data.input_variables?.join(', ') || ''}
          onChange={(e) =>
            handleChange(
              'input_variables',
              e.target.value.split(',').map((s) => s.trim()).filter(Boolean)
            )
          }
          placeholder="smell_intensity, has_symptoms"
        />
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Output Variable</label>
        <input
          type="text"
          style={styles.input}
          value={data.output_variable || ''}
          onChange={(e) => handleChange('output_variable', e.target.value)}
          placeholder="predicted_risk"
        />
      </div>
    </>
  );

  const renderWaitForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Wait Condition</label>
        <textarea
          style={styles.textarea}
          value={data.wait_condition || ''}
          onChange={(e) => handleChange('wait_condition', e.target.value)}
          rows={3}
          placeholder="e.g., Await sensor reading update"
        />
        <div style={styles.helpText}>Describe what event or condition to wait for</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Timeout (seconds)</label>
        <input
          type="number"
          style={styles.input}
          value={data.timeout || ''}
          onChange={(e) => handleChange('timeout', e.target.value ? Number(e.target.value) : '')}
          placeholder="300"
          min="0"
        />
        <div style={styles.helpText}>Maximum wait time before timeout action triggers</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Timeout Action</label>
        <CustomSelect
          value={data.timeout_action || 'continue'}
          onChange={(v) => handleChange('timeout_action', v)}
          options={[
            { value: 'continue', label: 'Continue to next node' },
            { value: 'abort', label: 'Abort workflow' },
            { value: 'escalate', label: 'Escalate to supervisor' },
          ]}
        />
        <div style={styles.helpText}>What happens when the timeout is reached</div>
      </div>
    </>
  );

  const renderParallelForm = () => (
    <>
      <div style={{ ...styles.formGroup, marginBottom: '20px' }}>
        <div
          style={{
            padding: '12px',
            backgroundColor: '#ecfeff',
            borderRadius: '6px',
            fontSize: '13px',
            color: '#155e75',
          }}
        >
          Parallel nodes execute multiple branches simultaneously. Connect multiple outgoing edges to define branches.
        </div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Merge Strategy</label>
        <CustomSelect
          value={data.merge_strategy || 'all'}
          onChange={(v) => handleChange('merge_strategy', v)}
          options={[
            { value: 'all', label: 'Wait for all branches to complete' },
            { value: 'any', label: 'Continue when first branch completes' },
          ]}
        />
        <div style={styles.helpText}>How to handle convergence of parallel branches</div>
      </div>
    </>
  );

  const renderHumanOverrideForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Override Instruction</label>
        <textarea
          style={styles.textarea}
          value={data.override_instruction || ''}
          onChange={(e) => handleChange('override_instruction', e.target.value)}
          rows={4}
          placeholder="e.g., Review incident severity and confirm dispatch"
        />
        <div style={styles.helpText}>Instructions displayed to the human operator</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Assigned Role</label>
        <input
          type="text"
          style={styles.input}
          value={data.assigned_role || ''}
          onChange={(e) => handleChange('assigned_role', e.target.value)}
          placeholder="supervisor"
        />
        <div style={styles.helpText}>Role responsible for handling this step</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Escalation Timeout (minutes)</label>
        <input
          type="number"
          style={styles.input}
          value={data.escalation_timeout || ''}
          onChange={(e) => handleChange('escalation_timeout', e.target.value ? Number(e.target.value) : '')}
          placeholder="30"
          min="0"
        />
        <div style={styles.helpText}>Auto-escalate if no response within this time</div>
      </div>
    </>
  );

  const renderTimerForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Timer Label</label>
        <input
          type="text"
          style={styles.input}
          value={data.timer_label || ''}
          onChange={(e) => handleChange('timer_label', e.target.value)}
          placeholder="e.g., Wait for cooldown period"
        />
        <div style={styles.helpText}>Descriptive label for this timer</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Duration (seconds)</label>
        <input
          type="number"
          style={styles.input}
          value={data.duration || ''}
          onChange={(e) => handleChange('duration', e.target.value ? Number(e.target.value) : '')}
          placeholder="60"
          min="0"
        />
        <div style={styles.helpText}>Timer duration in seconds</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Timeout Action</label>
        <CustomSelect
          value={data.timeout_action || 'continue'}
          onChange={(v) => handleChange('timeout_action', v)}
          options={[
            { value: 'continue', label: 'Continue to next node' },
            { value: 'abort', label: 'Abort workflow' },
            { value: 'escalate', label: 'Escalate to supervisor' },
          ]}
        />
        <div style={styles.helpText}>What happens when the timer expires</div>
      </div>
    </>
  );

  const renderNotificationForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Notification Message</label>
        <textarea
          style={styles.textarea}
          value={data.notification_message || ''}
          onChange={(e) => handleChange('notification_message', e.target.value)}
          rows={4}
          placeholder="e.g., Gas leak detected at location X"
        />
        <div style={styles.helpText}>Message content for the notification</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Channel</label>
        <CustomSelect
          value={data.channel || 'in_app'}
          onChange={(v) => handleChange('channel', v)}
          options={[
            { value: 'in_app', label: 'In-App' },
            { value: 'email', label: 'Email' },
            { value: 'sms', label: 'SMS' },
            { value: 'push', label: 'Push Notification' },
          ]}
        />
        <div style={styles.helpText}>Delivery channel for the notification</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Recipient</label>
        <input
          type="text"
          style={styles.input}
          value={data.recipient || ''}
          onChange={(e) => handleChange('recipient', e.target.value)}
          placeholder="e.g., operations_team"
        />
        <div style={styles.helpText}>Who should receive this notification</div>
      </div>
    </>
  );

  const renderAlertForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Alert Message</label>
        <textarea
          style={styles.textarea}
          value={data.alert_message || ''}
          onChange={(e) => handleChange('alert_message', e.target.value)}
          rows={4}
          placeholder="e.g., Critical gas leak requires immediate attention"
        />
        <div style={styles.helpText}>Alert message to be raised</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Severity</label>
        <CustomSelect
          value={data.severity || 'medium'}
          onChange={(v) => handleChange('severity', v)}
          options={[
            { value: 'low', label: 'Low' },
            { value: 'medium', label: 'Medium' },
            { value: 'high', label: 'High' },
            { value: 'critical', label: 'Critical' },
          ]}
        />
        <div style={styles.helpText}>Alert severity level</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Alert Type</label>
        <input
          type="text"
          style={styles.input}
          value={data.alert_type || ''}
          onChange={(e) => handleChange('alert_type', e.target.value)}
          placeholder="e.g., safety_hazard"
        />
        <div style={styles.helpText}>Category or type of alert</div>
      </div>
    </>
  );

  const renderEscalationForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Escalation Reason</label>
        <textarea
          style={styles.textarea}
          value={data.escalation_reason || ''}
          onChange={(e) => handleChange('escalation_reason', e.target.value)}
          rows={4}
          placeholder="e.g., Incident severity exceeds team authority"
        />
        <div style={styles.helpText}>Reason for escalating this incident</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Escalation Level</label>
        <input
          type="number"
          style={styles.input}
          value={data.escalation_level || ''}
          onChange={(e) => handleChange('escalation_level', e.target.value ? Number(e.target.value) : '')}
          placeholder="1"
          min="1"
          max="5"
        />
        <div style={styles.helpText}>Escalation level (1-5, higher = more urgent)</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Target Role</label>
        <input
          type="text"
          style={styles.input}
          value={data.target_role || ''}
          onChange={(e) => handleChange('target_role', e.target.value)}
          placeholder="e.g., supervisor"
        />
        <div style={styles.helpText}>Role to escalate to</div>
      </div>
    </>
  );

  const renderScriptForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Script Code</label>
        <textarea
          style={{ ...styles.textarea, fontFamily: 'monospace' }}
          value={data.script_code || ''}
          onChange={(e) => handleChange('script_code', e.target.value)}
          rows={6}
          placeholder={"result_a = int(value) * 2\nresult_b = int(value) + 10"}
        />
        <div style={styles.helpText}>Python code to execute</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Language</label>
        <CustomSelect
          value={data.script_language || 'python'}
          onChange={(v) => handleChange('script_language', v)}
          options={[
            { value: 'python', label: 'Python' },
            { value: 'javascript', label: 'JavaScript' },
          ]}
        />
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Output Variables</label>
        <input
          type="text"
          style={styles.input}
          value={data.output_variables || ''}
          onChange={(e) => handleChange('output_variables', e.target.value)}
          placeholder="result_a, result_b"
        />
        <div style={styles.helpText}>Comma-separated variable names to store from script</div>
      </div>
    </>
  );

  const renderDataFetchForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Source Name</label>
        <input
          type="text"
          style={styles.input}
          value={data.source_name || ''}
          onChange={(e) => handleChange('source_name', e.target.value)}
          placeholder="e.g., weather_api"
        />
        <div style={styles.helpText}>Name of the data source</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Endpoint</label>
        <input
          type="text"
          style={styles.input}
          value={data.endpoint || ''}
          onChange={(e) => handleChange('endpoint', e.target.value)}
          placeholder="e.g., /api/v1/readings"
        />
        <div style={styles.helpText}>API endpoint or data path</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Query Parameters</label>
        <input
          type="text"
          style={styles.input}
          value={data.query_params || ''}
          onChange={(e) => handleChange('query_params', e.target.value)}
          placeholder="e.g., location=site_a&type=gas"
        />
        <div style={styles.helpText}>Query string parameters for the request</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Output Variable</label>
        <input
          type="text"
          style={styles.input}
          value={data.output_variable || ''}
          onChange={(e) => handleChange('output_variable', e.target.value)}
          placeholder="fetched_data"
        />
        <div style={styles.helpText}>Variable to store the fetched data</div>
      </div>
    </>
  );

  const renderSubWorkflowForm = () => (
    <>
      <div style={styles.formGroup}>
        <label style={styles.label}>Label</label>
        <input
          type="text"
          style={styles.input}
          value={data.label || ''}
          onChange={(e) => handleChange('label', e.target.value)}
          placeholder="Manufacturer-specific triage"
        />
        <div style={styles.helpText}>Optional display label for the node</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Workflow ID</label>
        <input
          type="text"
          style={styles.input}
          value={data.workflow_id || ''}
          onChange={(e) => handleChange('workflow_id', e.target.value)}
          placeholder="tenant_demo_co_alarm_fireangel_v1"
        />
        <div style={styles.helpText}>Exact workflow to invoke. Use this when the target is fixed.</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Workflow ID Template</label>
        <input
          type="text"
          style={styles.input}
          value={data.workflow_id_template || ''}
          onChange={(e) => handleChange('workflow_id_template', e.target.value)}
          placeholder="{{manufacturer_workflow_id}}"
        />
        <div style={styles.helpText}>Optional template using variables from earlier questions.</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Use Case Fallback</label>
        <input
          type="text"
          style={styles.input}
          value={data.use_case || ''}
          onChange={(e) => handleChange('use_case', e.target.value)}
          placeholder="co_alarm_fireangel"
        />
        <div style={styles.helpText}>Optional fallback if you want the engine to resolve by use case instead of workflow ID.</div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Result Prefix</label>
        <input
          type="text"
          style={styles.input}
          value={data.result_prefix || ''}
          onChange={(e) => handleChange('result_prefix', e.target.value)}
          placeholder="manufacturer_triage"
        />
        <div style={styles.helpText}>Stores returned values like `manufacturer_triage_outcome` and `manufacturer_triage_message`.</div>
      </div>
    </>
  );

  return (
    <div style={{ padding: '16px' }}>
      <div style={{ marginBottom: '24px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '700', marginBottom: '8px' }}>
          Node Properties
        </h3>
        <div style={{ fontSize: '13px', color: '#6b7280' }}>
          ID: <code style={{ fontFamily: 'monospace' }}>{node.id}</code>
        </div>
        <div style={{ fontSize: '13px', color: '#6b7280', marginTop: '4px' }}>
          Type: <strong>{node.type}</strong>
        </div>
      </div>

      {node.type === 'QUESTION' && renderQuestionForm()}
      {node.type === 'CONDITION' && renderConditionForm()}
      {node.type === 'SWITCH' && renderConditionForm()}
      {node.type === 'DECISION' && renderDecisionForm()}
      {node.type === 'CALCULATE' && renderCalculateForm()}
      {node.type === 'ML_MODEL' && renderMLModelForm()}
      {node.type === 'WAIT' && renderWaitForm()}
      {node.type === 'PARALLEL' && renderParallelForm()}
      {node.type === 'HUMAN_OVERRIDE' && renderHumanOverrideForm()}
      {node.type === 'TIMER' && renderTimerForm()}
      {node.type === 'NOTIFICATION' && renderNotificationForm()}
      {node.type === 'ALERT' && renderAlertForm()}
      {node.type === 'ESCALATION' && renderEscalationForm()}
      {node.type === 'SCRIPT' && renderScriptForm()}
      {node.type === 'DATA_FETCH' && renderDataFetchForm()}
      {node.type === 'SUB_WORKFLOW' && renderSubWorkflowForm()}

      <button
        style={styles.deleteButton}
        onClick={() => onDelete(node.id)}
        onMouseEnter={(e) => {
          e.target.style.backgroundColor = '#dc2626';
        }}
        onMouseLeave={(e) => {
          e.target.style.backgroundColor = '#ef4444';
        }}
      >
        Delete Node
      </button>
    </div>
  );
};

export default NodePropertiesForm;
