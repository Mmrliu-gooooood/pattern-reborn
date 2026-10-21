import { useEffect, useRef, useState } from 'react';
import { api } from './api.js';

/** Drafts are recoverable work, distinct from published extraction/design versions. */
export function useDraft({ project, kind, value, dirty, busy, restore }) {
  const key = `pattern-reborn:draft:${project.id}:${kind}`;
  const [pending, setPending] = useState(null), [ready, setReady] = useState(false), [status, setStatus] = useState('');
  const [clearing, setClearing] = useState(false);
  const chain = useRef(Promise.resolve()), timer = useRef(null), epoch = useRef(0);
  const restoreRef = useRef(restore); restoreRef.current = restore;
  const serialized = JSON.stringify(value);
  useEffect(() => {
    let alive = true;
    let local;
    try { local = JSON.parse(localStorage.getItem(key)); } catch { /* Server copy remains authoritative. */ }
    api(`/projects/${project.id}/drafts/${kind}`).then(({ draft }) => {
      if (!alive) return;
      const recovered = local && (!draft || local.saved_at > draft.saved_at) ? local : draft;
      if (recovered) setPending({ ...recovered, stale: recovered.base_revision !== project.revision });
      setReady(true);
    }).catch(() => { if (alive) { setPending(local ? { ...local, stale: local.base_revision !== project.revision } : null); setReady(true); setStatus('草稿服务暂不可用，将保留浏览器副本'); } });
    return () => { alive = false; clearTimeout(timer.current); };
  }, [key]);
  useEffect(() => {
    clearTimeout(timer.current);
    if (!ready || pending || clearing || !dirty || busy || value === null) return;
    const payload = { base_revision: project.revision, data: value };
    try { localStorage.setItem(key, JSON.stringify({ ...payload, saved_at: new Date().toISOString() })); } catch { setStatus('浏览器空间不足，正在保存到本地项目'); }
    setStatus('草稿待保存…');
    const generation = epoch.current;
    timer.current = setTimeout(() => {
      chain.current = chain.current.catch(() => {}).then(async () => {
        if (generation !== epoch.current) return;
        try { await api(`/projects/${project.id}/drafts/${kind}`, { method: 'PUT', body: JSON.stringify(payload) }); if (generation === epoch.current) setStatus('草稿已自动保存'); }
        catch (e) { if (generation === epoch.current) setStatus(`草稿未同步：${e.message}`); }
      });
    }, 800);
    return () => clearTimeout(timer.current);
  }, [serialized, dirty, busy, ready, pending, clearing, project.revision, key]);
  async function clear() {
    setClearing(true); epoch.current++; clearTimeout(timer.current); setPending(null);
    try { localStorage.removeItem(key); } catch { /* Browser storage may be disabled. */ }
    await chain.current.catch(() => {});
    try { await api(`/projects/${project.id}/drafts/${kind}`, { method: 'DELETE' }); setStatus(''); }
    catch { setStatus('已保存作品；旧草稿清理失败，重开时可丢弃'); }
    finally { setClearing(false); }
  }
  function recover() { if (!pending?.stale) { restoreRef.current(pending.data); setPending(null); setStatus('已恢复草稿，请预览并保存'); } }
  return { pending, status, ready, clearing, recover, clear };
}
