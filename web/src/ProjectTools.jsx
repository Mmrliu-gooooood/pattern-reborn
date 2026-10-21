import { useConfirm } from './useConfirm.jsx';
import { useEffect, useState } from 'react';
import { DownloadSimple, ClockCounterClockwise } from '@phosphor-icons/react';
import { api } from './api.js';
import { Modal } from './components.jsx';

export function DraftNotice({ draft }) {
  return draft.pending ? <div className="draft-notice" role="status"><span>{draft.pending.stale ? '发现旧草稿，但项目版本已改变。为避免覆盖新成果，请丢弃旧草稿。' : '发现未完成的草稿，可以继续上次编辑。'}</span>{!draft.pending.stale && <button onClick={draft.recover}>恢复草稿</button>}<button onClick={draft.clear}>丢弃草稿</button></div> : draft.status ? <p className="draft-status" role="status">{draft.status}</p> : null;
}

export function VersionButton({ project, disabled, restored, notice }) {
  const [open, setOpen] = useState(false);
  return <><button className="history-button" disabled={disabled} title="版本与方案" onClick={() => setOpen(true)}><ClockCounterClockwise size={20} /><span>版本</span></button>{open && <Versions project={project} close={() => setOpen(false)} restored={value => { setOpen(false); restored(value); }} notice={notice} />}</>;
}

function Versions({ project, close, restored, notice }) {
  const [confirm, confirmation] = useConfirm();
  const [versions, setVersions] = useState([]), [name, setName] = useState(''), [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function refresh() { try { setVersions((await api(`/projects/${project.id}/versions`)).versions); } catch (e) { setError(e.message); } }
  useEffect(() => { refresh(); }, [project.id]);
  async function create(event) {
    event.preventDefault(); setBusy(true); setError('');
    try { await api(`/projects/${project.id}/versions`, { method:'POST', body:JSON.stringify({ revision:project.revision, name }) }); setName(''); await refresh(); notice('方案已命名保存'); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function recover(version) {
    if (!await confirm(`恢复「${version.name}」？当前已保存状态会先备份，未保存的页面编辑将被替换。`)) return;
    setBusy(true); setError('');
    try { const value = await api(`/projects/${project.id}/versions/${version.id}/restore`, { method:'POST', body:JSON.stringify({ revision:project.revision }) }); restored(value.project); notice('版本已恢复，恢复前的状态也已保留'); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  const compared = versions.filter(v => selected.includes(v.id));
  return <Modal title="版本与方案" close={() => !busy && close()}><div className="versions-panel">{confirmation}
    <p className="tool-hint">每次保存会留下版本。命名保留喜欢的方案，勾选两份可并排比较。</p>
    <form className="version-name" onSubmit={create}><input aria-label="方案名称" required maxLength={80} placeholder="例如：青花四方 · 第一稿" value={name} onChange={e => setName(e.target.value)} /><button className="primary" disabled={busy || !name.trim()}>保存当前方案</button></form>
    {error && <p className="error-message" role="alert">{error}</p>}
    {compared.length > 0 && <div className="version-comparison">{compared.map(v => <figure key={v.id}><img src={v.pattern_url || v.result_url} alt={v.name} /><figcaption>{v.name}</figcaption></figure>)}</div>}
    <div className="version-list">{!versions.length && <p className="tool-hint">保存一次纹样或作品后，这里会出现版本。</p>}{versions.map(v => <article key={v.id}><label><input aria-label={`比较${v.name}`} type="checkbox" disabled={(!v.has_result && !v.has_pattern) || (!selected.includes(v.id) && selected.length >= 2)} checked={selected.includes(v.id)} onChange={e => setSelected(e.target.checked ? [...selected,v.id] : selected.filter(id => id !== v.id))} /><span><strong>{v.name}</strong><small>{v.automatic ? '自动版本' : '命名方案'} · {new Date(v.created_at).toLocaleString('zh-CN')}</small></span></label><button className="outline" disabled={busy} onClick={() => recover(v)}>恢复</button></article>)}</div>
    <a className="download-link" href={`/api/projects/${project.id}/backup`} download><DownloadSimple size={18} />下载完整项目备份</a>
  </div></Modal>;
}

export function ImportProject({ close, created }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try { created(await api('/projects/import', { method:'POST', body:new FormData(event.currentTarget) })); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <Modal title="导入项目备份" close={() => !busy && close()}><form className="project-form" onSubmit={submit}><p className="tool-hint">恢复为一个独立项目，原有项目不会被覆盖。</p><label>备份 ZIP<input required type="file" name="file" accept=".zip" /></label><label>新项目名称（可选）<input name="name" maxLength={80} /></label>{error && <p className="error-message" role="alert">{error}</p>}<button className="primary" disabled={busy}>{busy ? '正在校验并导入…' : '导入项目'}</button></form></Modal>;
}
