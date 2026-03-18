import { useState, useRef, useEffect } from 'react';

/**
 * CustomSelect — styled dropdown replacement for native <select>.
 *
 * Props:
 *  - value        : current selected value (string)
 *  - onChange      : (value) => void
 *  - options       : [{ value, label }]
 *  - placeholder   : text when nothing selected (default "Select…")
 *  - disabled      : boolean
 *  - style         : override styles on the trigger button
 *  - menuStyle     : override styles on the dropdown panel
 *  - small         : compact size (pagination / inline selects)
 *  - className     : optional className forwarded to wrapper
 */
const CustomSelect = ({
  value,
  onChange,
  options = [],
  placeholder = 'Select\u2026',
  disabled = false,
  style = {},
  menuStyle = {},
  small = false,
  className,
}) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const selected = options.find((o) => String(o.value) === String(value));

  const base = small ? S.triggerSmall : S.trigger;

  return (
    <div ref={ref} style={{ position: 'relative', ...style }} className={className}>
      <button
        type="button"
        onClick={() => !disabled && setOpen((p) => !p)}
        style={{
          ...base,
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.5 : 1,
        }}
      >
        <span style={S.label}>{selected ? selected.label : placeholder}</span>
        <svg
          width={small ? 12 : 14} height={small ? 12 : 14}
          viewBox="0 0 20 20" fill="none"
          style={{ flexShrink: 0, marginLeft: 6, transform: open ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.2s' }}
        >
          <path d="M5 7.5L10 12.5L15 7.5" stroke="#6b7280" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && options.length > 0 && (
        <div style={{ ...S.menu, ...menuStyle }}>
          {options.map((o) => {
            const active = String(o.value) === String(value);
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => { onChange(o.value); setOpen(false); }}
                style={{
                  ...S.item,
                  ...(small ? S.itemSmall : {}),
                  background: active ? '#eff6ff' : 'transparent',
                  color: active ? '#1d4ed8' : '#374151',
                  fontWeight: active ? 700 : 500,
                }}
                onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = '#f3f4f6'; }}
                onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={S.label}>{o.label}</span>
                {active && (
                  <svg width="16" height="16" viewBox="0 0 20 20" fill="none" style={{ flexShrink: 0 }}>
                    <path d="M5 10L8.5 13.5L15 7" stroke="#1d4ed8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

const S = {
  trigger: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
    border: '1px solid #d1d5db',
    borderRadius: '0.5rem',
    padding: '0.5rem 0.75rem',
    background: '#fff',
    color: '#111827',
    fontSize: '0.82rem',
    fontWeight: 600,
    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
    transition: 'border-color 0.15s, box-shadow 0.15s',
  },
  triggerSmall: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
    border: '1px solid #d1d5db',
    borderRadius: '6px',
    padding: '3px 8px',
    background: '#fff',
    color: '#374151',
    fontSize: '0.76rem',
    fontWeight: 600,
    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
    transition: 'border-color 0.15s',
  },
  label: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  menu: {
    position: 'absolute',
    top: 'calc(100% + 4px)',
    left: 0,
    right: 0,
    background: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: '0.5rem',
    boxShadow: '0 10px 25px rgba(0,0,0,0.1), 0 4px 10px rgba(0,0,0,0.05)',
    zIndex: 50,
    maxHeight: 220,
    overflowY: 'auto',
    padding: '4px 0',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
    border: 'none',
    padding: '0.5rem 0.75rem',
    fontSize: '0.82rem',
    cursor: 'pointer',
    textAlign: 'left',
    transition: 'background 0.12s',
  },
  itemSmall: {
    padding: '0.35rem 0.6rem',
    fontSize: '0.76rem',
  },
};

export default CustomSelect;
