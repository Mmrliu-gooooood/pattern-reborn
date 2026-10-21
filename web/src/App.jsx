import { useEffect, useState } from 'react';
import { Archive, FolderSimple, GearSix } from '@phosphor-icons/react';
import { api } from './api.js';
import { Brand, Ornament, Modal } from './components.jsx';
import { Library, NewProject, Rename } from './Library.jsx';
import { Workspace } from './Workspace.jsx';
import { ImportProject } from './ProjectTools.jsx';
import { Settings } from './Settings.jsx';

export function App() {
  const [library, setLibrary] = useState({ projects: [], examples: [], categories: [] });
  const [project, setProject] = useState(null), [archived, setArchived] = useState(false);
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [toast, setToast] = useState('');
  const [modal, setModal] = useState(null), [opening, setOpening] = useState(false);
  async function refresh() { try { setLibrary(await api('/library')); setError(''); } catch (e) { setError(e.message); } finally { setLoading(false); } }
  useEffect(() => { refresh(); }, []);
  useEffect(() => { if (toast) { const timer = setTimeout(() => setToast(''), 4200); return () => clearTimeout(timer); } }, [toast]);
  async function open(item) {
    if (opening) return; setOpening(true); setError('');
    try { setProject(await api(item.demo ? `/examples/${item.id}/open` : `/projects/${item.id}`, item.demo ? { method: 'POST' } : {})); }
    catch (e) { setError(e.message); } finally { setOpening(false); }
  }
  async function change(item, data) {
    await api(`/projects/${item.id}`, { method: 'PATCH', body: JSON.stringify({ revision: item.revision, ...data }) });
    await refresh(); setToast(data.name ? '项目已重命名' : data.archived ? '项目已归档，可随时恢复' : '项目已恢复');
  }
  async function duplicate(item) {
    if (opening) return;
    setOpening(true); setError(''); setToast('正在复制项目…');
    try {
      await api(`/projects/${item.id}/duplicate`, {method:'POST',body:JSON.stringify({revision:item.revision,name:`${item.name.slice(0,75)} · 副本`})});
      await refresh(); setToast('已创建独立副本');
    } catch(e) { setError(e.message); setToast(''); }
    finally { setOpening(false); }
  }
  return <>
    {project ? <Workspace key={project.id} initial={project} notice={setToast} back={() => { setProject(null); refresh(); }} /> : <div className="library-shell">
      <aside className="sidebar"><Brand /><nav aria-label="主导航"><button className={!archived ? 'active' : ''} onClick={() => setArchived(false)}><FolderSimple size={20} /><span>项目库</span></button><button className={archived ? 'active' : ''} onClick={() => setArchived(true)}><Archive size={20} /><span>已归档</span></button></nav><Ornament /><button className="settings-button" aria-label="设置" onClick={() => setModal({ type: 'settings' })}><GearSix size={20} /><span>设置</span></button></aside>
      <main className="library-main">{error && <div className="error-message" role="alert">{error}<button onClick={refresh}>重试</button></div>}
        <Library library={library} archived={archived} loading={loading} opening={opening} open={open} create={() => setModal({ type: 'new' })} importProject={() => setModal({ type:'import' })} duplicate={duplicate} rename={item => setModal({ type: 'rename', item })} archive={item => change(item, { archived: !item.archived }).catch(e => setError(e.message))} />
      </main>
    </div>}
    {toast && <div className="toast" role="status">{toast}</div>}
    {modal?.type === 'new' && <NewProject categories={library.categories} close={() => setModal(null)} created={value => { setModal(null); setProject(value); }} />}
    {modal?.type === 'rename' && <Rename item={modal.item} close={() => setModal(null)} save={name => change(modal.item, { name })} />}
    {modal?.type === 'settings' && <Settings close={() => { setModal(null); refresh(); }} />}
    {modal?.type === 'import' && <ImportProject close={() => setModal(null)} created={value => { setModal(null); setProject(value); setToast('备份已恢复为独立项目'); }} />}
  </>;
}
