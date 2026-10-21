import { useEffect, useRef } from 'react';
import { X } from '@phosphor-icons/react';
export function Brand() { return <div className="brand"><div className="brand-name"><img src="/assets/seal-wen-v2.png" alt="纹字篆刻印章" /><span>纹启新生</span></div><div className="brand-rule" /></div>; }
export function Ornament() { return <img className="botanical" src="/assets/botanical.png" alt="" aria-hidden="true" />; }
export function IconButton({ label, children, ...props }) { return <button className="icon-button" aria-label={label} title={label} {...props}>{children}</button>; }
export function Modal({ title, close, children }) {
  const box = useRef(null), closeRef = useRef(close); closeRef.current = close;
  useEffect(() => {
    const previous = document.activeElement; box.current.querySelector('input,button')?.focus();
    function key(event) {
      if (box.current !== [...document.querySelectorAll('[role="dialog"]')].at(-1)) return;
      if (event.key === 'Escape') closeRef.current();
      if (event.key !== 'Tab') return;
      const items = [...box.current.querySelectorAll('button:not(:disabled),input:not(:disabled):not([type=hidden]),textarea:not(:disabled),select:not(:disabled),a[href],summary')].filter(node => node.getClientRects().length > 0);
      const first = items[0], last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); previous?.focus(); };
  }, []);
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && close()}><section ref={box} className="modal" role="dialog" aria-modal="true" aria-label={title}><header><h2>{title}</h2><IconButton label="关闭" onClick={close}><X size={22} /></IconButton></header>{children}</section></div>;
}
