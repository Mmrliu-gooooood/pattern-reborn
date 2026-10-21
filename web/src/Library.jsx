import { useEffect, useState } from 'react';
import { ArrowSquareOut, CaretDown, CaretRight, DotsThreeVertical, FileImage, FolderSimple, MagnifyingGlass, Plus } from '@phosphor-icons/react';
import { api } from './api.js';
import { Select } from './Select.jsx';
import { IconButton, Modal } from './components.jsx';
const date = value => new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(new Date(value));
const groups = [{ id: 'all', name: '全部' }, { id: 'embroidery_brocade', name: '织绣' }, { id: 'dyeing_textile', name: '印染' }, { id: 'folk_painting', name: '民间绘画' }];

export function Library({ library, archived, loading, opening, open, create, rename, archive, duplicate, importProject }) {
  const [query, setQuery] = useState(''), [category, setCategory] = useState('all'), [sort, setSort] = useState('recent'), [menu, setMenu] = useState(null), [showExamples, setShowExamples] = useState(false);
  const hasProjects = library.projects.some(p => !p.archived);
  const examplesOnly = !archived && (showExamples || (!hasProjects && !loading));
  const items = (examplesOnly ? library.examples : library.projects.filter(p => p.archived === archived)).filter(p => (category === 'all' || p.category === category) && p.name.toLowerCase().includes(query.toLowerCase()));
  if (sort === 'name') items.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
  useEffect(() => { if (!menu) return; const close = () => setMenu(null); document.addEventListener('click', close); return () => document.removeEventListener('click', close); }, [menu]);
  useEffect(() => { setMenu(null); setCategory('all'); }, [archived]);
  return <>
    <header className="library-header"><div className="page-heading"><h1>{archived ? '已归档' : '我的项目'}</h1><p>每一份纹样，都有来处。</p></div><div className="header-actions"><label className="search"><MagnifyingGlass size={19} /><input aria-label="搜索项目" placeholder="搜索项目名称" value={query} onChange={e => setQuery(e.target.value)} /></label><button className="outline import-button" onClick={importProject}>导入备份</button><button className="primary" onClick={create}><Plus size={19} />新建项目</button></div></header>
    <div className="library-filters"><div className="category-tabs" aria-label="纹样分类">{groups.map(c => <button key={c.id} aria-pressed={category === c.id} className={category === c.id ? 'selected' : ''} onClick={() => setCategory(c.id)}>{c.name}</button>)}<Select label="更多工艺分类" variant="quiet" value={groups.some(c => c.id === category) ? '' : category} onChange={value => value && setCategory(value)} options={[{ value: '', label: '更多工艺' }, ...library.categories.filter(c => !groups.some(g => g.id === c.id)).map(c => ({ value: c.id, label: c.name }))]} /></div><Select label="排序方式" variant="quiet" value={sort} onChange={setSort} options={[{ value: 'recent', label: '最近编辑' }, { value: 'name', label: '按名称' }]} /></div>
    <div className="collection-context"><span>{archived ? '暂存旧作，灵感仍在。' : examplesOnly ? '从一份真实的工艺素材，开始你的创作。' : `${items.length} 份创作，静待续写。`}</span>{!archived && <button disabled={!hasProjects} onClick={() => setShowExamples(!examplesOnly)}>{examplesOnly ? hasProjects ? '返回我的项目' : '示例素材 · 打开后创建本地项目' : '浏览示例素材'}<CaretRight size={14} /></button>}</div>
    {loading ? <div className="empty-state" role="status">正在打开项目库…</div> : !items.length ? <div className="empty-state"><FolderSimple size={36} /><h2>{query || category !== 'all' ? '没有找到匹配的纹样' : archived ? '还没有归档项目' : '从第一份纹样开始'}</h2><p>{query || category !== 'all' ? '换一个关键词或分类试试。' : '导入一张图像，保存一份自己的创作。'}</p>{!archived && <button className="primary" onClick={create}>新建项目</button>}</div> : <div className="project-grid">{items.map(item => <article className="project-card" key={item.id}>
      <button className="project-cover" onClick={() => open(item)} disabled={opening} aria-label={`打开${item.name}`}><img src={item.image} alt={item.name} loading="lazy" /><span className="cover-action">{item.demo ? '以此开始' : '继续编辑'}<ArrowSquareOut size={18} /></span>{item.has_result && <span className="saved-mark" title="已保存提取结果" />}</button>
      <div className="project-caption"><div><button className="project-title" onClick={() => open(item)} disabled={opening}>{item.name}</button><p>{item.category_label}<span>·</span>{item.demo ? '工艺参考' : date(item.updated_at)}</p></div>{!item.demo && <div className="card-menu-wrap"><IconButton disabled={opening} label={`${item.name}的更多操作`} aria-expanded={menu === item.id} onClick={e => { e.stopPropagation(); setMenu(menu === item.id ? null : item.id); }}><DotsThreeVertical size={22} /></IconButton>{menu === item.id && <div className="card-menu"><button onClick={() => rename(item)}>重命名</button><button onClick={() => duplicate(item)}>复制项目</button><a href={`/api/projects/${item.id}/backup`} download>下载完整备份</a><button onClick={() => archive(item)}>{item.archived ? '恢复项目' : '归档项目'}</button></div>}</div>}</div>
    </article>)}</div>}
    <footer className="library-footer"><span>纹样有源 · 创作有迹</span><span>本地工作台</span></footer>
  </>;
}

export function NewProject({ categories, close, created }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [fileName, setFileName] = useState(''), [category, setCategory] = useState(categories[0]?.id || 'paper_cutting');
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(''); const body = new FormData(event.currentTarget);
    try { if (body.get('file').size > 24 * 1024 * 1024) throw new Error('请选择小于 24 MB 的图像。'); created(await api('/projects', { method: 'POST', body })); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <Modal title="新建纹样项目" close={() => !busy && close()}><form onSubmit={submit} className="project-form"><label>项目名称<input name="name" required maxLength={80} placeholder="为这份纹样取个名字" /></label><div className="form-field"><span>工艺类别</span><Select label="工艺类别" name="category" value={category} onChange={setCategory} options={categories.map(c => ({ value: c.id, label: c.name }))} /></div><label className="file-field"><FileImage size={30} /><strong>{fileName || '选择一张原始图像'}</strong><span>PNG、JPEG、WebP、BMP、TIFF · 小于 24 MB</span><input name="file" type="file" required accept=".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff" onChange={e => setFileName(e.target.files[0]?.name || '')} /></label><p className="form-note">原始图像会单独保存，每次编辑都会留下新的提取结果。</p>{error && <p className="error-message" role="alert">{error}</p>}<button className="primary" disabled={busy} type="submit">{busy ? '正在创建…' : '创建并开始提取'}</button></form></Modal>;
}
export function Rename({ item, close, save }) {
  const [name, setName] = useState(item.name), [busy, setBusy] = useState(false), [error, setError] = useState('');
  return <Modal title="重命名项目" close={() => !busy && close()}><form className="project-form" onSubmit={async e => { e.preventDefault(); setBusy(true); try { await save(name); close(); } catch (err) { setError(err.message); } finally { setBusy(false); } }}><label>项目名称<input value={name} onChange={e => setName(e.target.value)} required maxLength={80} /></label>{error && <p role="alert" className="error-message">{error}</p>}<button className="primary" disabled={busy || !name.trim()}>保存名称</button></form></Modal>;
}
