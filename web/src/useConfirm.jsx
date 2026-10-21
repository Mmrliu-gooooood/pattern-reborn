import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Modal } from './components.jsx';

export function useConfirm() {
  const [message, setMessage] = useState('');
  const resolve = useRef(null);
  useEffect(() => () => resolve.current?.(false), []);
  function finish(answer) { resolve.current?.(answer); resolve.current = null; setMessage(''); }
  function confirm(text) {
    resolve.current?.(false);
    setMessage(text);
    return new Promise(done => { resolve.current = done; });
  }
  const dialog = message ? createPortal(<Modal title="确认操作" close={() => finish(false)}><p className="confirm-copy">{message}</p><div className="settings-actions"><button className="outline" onClick={() => finish(false)}>取消</button><button className="primary" onClick={() => finish(true)}>确认继续</button></div></Modal>, document.body) : null;
  return [confirm, dialog];
}
