import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { CaretDown, Check } from '@phosphor-icons/react';

/** A shared, keyboard-operable select whose popup does not inherit OS styling. */
export function Select({ value, onChange, options, label, name, disabled = false, variant = '' }) {
  const id = useId(), trigger = useRef(null), popup = useRef(null), search = useRef({ text: '', at: 0 });
  const [open, setOpen] = useState(false), [active, setActive] = useState(0), [position, setPosition] = useState({});
  const selected = options.findIndex(option => String(option.value) === String(value));
  function show() { if (!disabled) { setActive(Math.max(0, selected)); setOpen(true); } }
  function choose(index) { onChange(options[index].value); setOpen(false); trigger.current?.focus(); }
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const rect = trigger.current.getBoundingClientRect();
      const height = Math.min(320, options.length * 42 + 12, window.innerHeight - 24);
      const width = Math.min(Math.max(rect.width, 210), window.innerWidth - 24);
      const below = window.innerHeight - rect.bottom - 12;
      const above = rect.top - 18, openBelow = below >= height || below >= above;
      const menuHeight = Math.min(height, Math.max(42, openBelow ? below : above));
      setPosition({ width, maxHeight: menuHeight, left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)), top: openBelow ? rect.bottom + 6 : Math.max(12, rect.top - menuHeight - 6) });
    };
    place(); window.addEventListener('resize', place); window.addEventListener('scroll', place, true);
    return () => { window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); };
  }, [open, options.length]);
  useEffect(() => {
    if (!open) return;
    const outside = event => { if (!trigger.current?.contains(event.target) && !popup.current?.contains(event.target)) setOpen(false); };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => { if (open) popup.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' }); }, [open, active]);
  function keyboard(event) {
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) event.preventDefault();
    if (event.key === 'Escape') { event.stopPropagation(); setOpen(false); return; }
    if (event.key === 'Tab') { setOpen(false); return; }
    if (event.key === 'Enter' || event.key === ' ') { if (open) choose(active); else show(); return; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!open) show(); else setActive(index => (index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length);
    } else if (event.key === 'Home') { setActive(0); setOpen(true); }
    else if (event.key === 'End') { setActive(options.length - 1); setOpen(true); }
    else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
      const now = Date.now(); search.current = { text: (now - search.current.at < 800 ? search.current.text : '') + event.key, at: now };
      const match = options.findIndex(option => option.label.toLowerCase().startsWith(search.current.text.toLowerCase()));
      if (match >= 0) { setActive(match); setOpen(true); }
    }
  }
  return <div className={`studio-select ${variant}`}>
    {name && <input type="hidden" name={name} value={value} />}
    <button ref={trigger} type="button" role="combobox" aria-label={label} aria-expanded={open} aria-controls={open ? id : undefined} aria-haspopup="listbox" aria-activedescendant={open ? `${id}-${active}` : undefined} disabled={disabled} className={open ? 'select-trigger open' : 'select-trigger'} onClick={() => open ? setOpen(false) : show()} onKeyDown={keyboard}>
      <span>{options[selected]?.label || label}</span><CaretDown size={14} />
    </button>
    {open && createPortal(<div ref={popup} id={id} role="listbox" aria-label={label} className="select-popup" style={position}>
      {options.map((option, index) => <div id={`${id}-${index}`} data-index={index} key={option.value} role="option" aria-selected={index === selected} className={`select-option ${index === selected ? 'selected' : ''} ${index === active ? 'focused' : ''}`} onPointerMove={() => setActive(index)} onPointerDown={event => event.preventDefault()} onClick={() => choose(index)}><span>{option.label}</span>{index === selected && <Check size={16} weight="bold" />}</div>)}
    </div>, document.body)}
  </div>;
}
