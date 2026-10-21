import { useConfirm } from './useConfirm.jsx';
import { useEffect, useReducer, useState } from 'react';
import { ArrowLeft, ArrowCounterClockwise, ArrowClockwise, ArrowSquareOut, ArrowsOut, CaretDown, DownloadSimple, Eraser, FileImage, Hand, Info, PaintBrush, Selection, FloppyDisk } from '@phosphor-icons/react';
import { api } from './api.js';
import { Select } from './Select.jsx';
import { Stages } from './Stages.jsx';
import { useDraft } from './useDraft.js';
import { DraftNotice, VersionButton } from './ProjectTools.jsx';
import { EditorCanvas } from './Canvas.jsx';
import { historyReducer, initialHistory } from './history.js';
import { Brand, Ornament, IconButton } from './components.jsx';

export function Editor({ initial, back, notice, navigate }) {
  const [confirm, confirmation] = useConfirm();
  const [project, setProject] = useState(initial);
  const firstDraft = { box: null, strokes: [], feather: 0, profile: initial.profile, ...initial.draft, extraction: { mode:'auto', color:'#B52B32', tolerance:24, minimum_area:16, fill_holes:false, smooth:0, ...initial.draft?.extraction } };
  const [history, dispatch] = useReducer(historyReducer, firstDraft, initialHistory);
  const draft = history.present, draftJSON = JSON.stringify(draft);
  const [savedJSON, setSavedJSON] = useState(JSON.stringify(firstDraft));
  const [tool, setTool] = useState('box'), [brush, setBrush] = useState(42), [zoom, setZoom] = useState(1), [pan, setPan] = useState({ x: 0, y: 0 });
  const [view, setView] = useState('source'), [working, setBusy] = useState(false), [error, setError] = useState('');
  const [preview, setPreview] = useState({ result: initial.result_url, mask: initial.mask_url, draft: JSON.stringify(firstDraft) });
  const dirty = draftJSON !== savedJSON, validPreview = preview.draft === draftJSON && preview.result;
  const change = value => dispatch({ type: 'set', value });
  const [capabilities, setCapabilities] = useState(null);
  useEffect(() => { api('/extraction/capabilities').then(setCapabilities).catch(() => {}); }, []);
  const draftStore = useDraft({ project, kind:'extract', value:draft, dirty, busy:working, restore:value => change({ ...firstDraft, ...value, extraction:{ ...firstDraft.extraction, ...value.extraction } }) });
  const busy = working || !draftStore.ready || Boolean(draftStore.pending) || draftStore.clearing;
  useEffect(() => { setView('source'); }, [draftJSON]);
  useEffect(() => { const guard = e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [dirty]);
  async function process(save) {
    if (busy) return;
    if (save && project.has_downstream && !await confirm('重新提取会使之前的分析、重组与导出结果失效。继续保存吗？')) return;
    setBusy(true); setError('');
    try {
      const value = await api(`/projects/${project.id}/${save ? 'save' : 'preview'}`, { method: 'POST', body: JSON.stringify({ ...draft, revision: project.revision }) });
      if (save) { await draftStore.clear(); setProject(value); setSavedJSON(draftJSON); setPreview({ result: value.result_url, mask: value.mask_url, draft: draftJSON }); notice('纹样已保存'); }
      else { setPreview({ ...value, draft: draftJSON }); if (value.empty) notice('未找到纹样，请尝试保留笔刷或调整选区'); }
      if (value.warnings?.length) notice(value.warnings.join('；'));
      setView('result');
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  useEffect(() => {
    const key = e => {
      if (!(e.ctrlKey || e.metaKey) || ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
      if (['z', 'y', 's'].includes(e.key.toLowerCase())) e.preventDefault();
      if (busy) return;
      if (e.key.toLowerCase() === 'z') dispatch({ type: e.shiftKey ? 'redo' : 'undo' });
      if (e.key.toLowerCase() === 'y') dispatch({ type: 'redo' });
      if (e.key.toLowerCase() === 's') process(true);
    }; window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key);
  });
  async function leave() { if (!busy && (!dirty || await confirm('还有未保存为版本的修改。已自动保存的草稿可下次恢复，返回项目库吗？'))) back(); }
  const image = view === 'source' || !validPreview ? project.source_url : preview[view];
  const chooseTool = value => { setTool(value); if (value !== 'hand') setView('source'); };
  const tools = [['box', Selection, '框选'], ['keep', PaintBrush, '保留'], ['remove', Eraser, '去除'], ['hand', Hand, '移动']];
  return <div className="editor-shell">{confirmation}<div className="editor-brand"><Brand /></div><header className="editor-header"><button className="back-button" disabled={busy} onClick={leave}><ArrowLeft size={20} /><span>项目库</span></button><div className="editor-title"><h1>{project.name}</h1><span className={dirty ? 'unsaved' : ''}>{dirty ? '有未保存修改' : project.has_result ? '已保存' : '开始提取'}</span></div><VersionButton project={project} disabled={busy} notice={notice} restored={async value => { await draftStore.clear(); navigate('extract', value); }} /><button className="primary" disabled={busy} onClick={() => process(true)}><FloppyDisk size={19} /><span>{working ? '处理中…' : '保存纹样'}</span></button></header>
    <aside className="asset-rail"><h2>素材<span>{project.has_result ? '02' : '01'}</span></h2><button className={view === 'source' ? 'asset selected' : 'asset'} onClick={() => setView('source')}><img src={project.source_url} alt="" /><span>原始图像</span></button>{validPreview && <button className={view === 'result' ? 'asset selected' : 'asset'} onClick={() => setView('result')}><img src={preview.result} alt="" /><span>提取纹样</span></button>}<Ornament /><p className="asset-note">留存原作<br />续写新意</p></aside>
    <main className="editing-region"><Stages stage="extract" ready={project.has_result && !dirty} disabled={busy} change={stage => { if (stage !== 'extract') navigate(stage, project); }} /><DraftNotice draft={draftStore} /><div className="editor-toolbar" role="toolbar" aria-label="画布工具">{tools.map(([value, Icon, title]) => <button key={value} disabled={busy} className={tool === value ? 'selected' : ''} aria-pressed={tool === value} onClick={() => chooseTool(value)}><Icon size={22} /><span>{title}</span></button>)}<div className="tool-divider" /><IconButton label="撤销 Ctrl+Z" disabled={busy || !history.past.length} onClick={() => dispatch({ type: 'undo' })}><ArrowCounterClockwise size={22} /></IconButton><IconButton label="重做 Ctrl+Shift+Z" disabled={busy || !history.future.length} onClick={() => dispatch({ type: 'redo' })}><ArrowClockwise size={22} /></IconButton></div>
      {error && <div className="error-message editor-error" role="alert">{error}<button onClick={() => setError('')}>关闭</button></div>}
      <EditorCanvas project={project} draft={draft} onChange={change} tool={tool} brush={brush} zoom={zoom} pan={pan} setPan={setPan} view={view} image={image} busy={busy} processing={working} />
      <div className="canvas-status"><Select label="画布缩放" variant="dark" value={zoom} onChange={value => setZoom(Number(value))} options={[0.5, 0.75, 1, 1.5, 2, 3].map(n => ({ value: n, label: `${n * 100}%` }))} /><button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}><ArrowsOut size={19} />自适应</button><span>{project.width} × {project.height}</span></div>
    </main>
    <aside className="inspector"><h2>提取工具</h2><div className="brush-switch">{tools.slice(1, 3).map(([value, Icon, title]) => <button key={value} disabled={busy} aria-pressed={tool === value} className={tool === value ? 'selected' : ''} onClick={() => chooseTool(value)}><Icon size={21} />{title}</button>)}</div>
      <label className="range-control">画笔大小<span><input aria-label="画笔大小" type="range" min="4" max="160" value={brush} onChange={e => setBrush(Number(e.target.value))} /><output>{brush}</output></span></label>
      <label className="range-control">边缘柔化<span><input aria-label="边缘柔化" disabled={busy} type="range" min="0" max="10" value={draft.feather} onChange={e => change({ ...draft, feather: Number(e.target.value) })} /><output>{draft.feather}</output></span></label>
      <p className="tool-hint">{tool === 'box' ? '拖动框选需要提取的纹样区域。' : tool === 'keep' ? '涂抹要保留的部分，再预览结果。' : tool === 'remove' ? '涂抹要去除的部分，再预览结果。' : '拖动图像，查看纹样的局部细节。'}</p><button className="outline preview-button" disabled={busy} onClick={() => process(false)}>{working ? '正在提取…' : '预览提取'}</button>
      <section className="view-section"><h2>视图</h2><div className="view-options">{[['source', '原图', project.source_url], ['mask', '蒙版', validPreview && preview.mask], ['result', '结果', validPreview && preview.result]].map(([value, title, src]) => <button key={value} className={view === value ? 'selected' : ''} disabled={!src} onClick={() => setView(value)}><span className="view-thumb">{src ? <img src={src} alt="" /> : <FileImage size={22} />}</span><span>{title}</span></button>)}</div></section>
      {project.result_url && !dirty && <a className="download-link" href={project.result_url + '&download=true'} download><DownloadSimple size={18} />导出透明 PNG</a>}
      <details className="advanced"><summary>提取设置</summary><div className="form-field"><span>提取方法</span><Select label="提取方法" disabled={busy} value={draft.extraction.mode} onChange={mode => change({ ...draft, extraction:{ ...draft.extraction,mode } })} options={[{value:'auto',label:'智能本地提取'},{value:'opencv',label:'经典轮廓提取'},{value:'color',label:'按颜色提取'},{value:'whole',label:'保留整张图像'},...(capabilities?.mobile_sam?.available ? [{value:'mobile_sam',label:'MobileSAM 精细提取'}] : [])]} /></div>
      {draft.extraction.mode === 'color' && <><label className="background-color">目标颜色<input type="color" aria-label="提取目标颜色" value={draft.extraction.color || '#B52B32'} disabled={busy} onChange={e => change({ ...draft,extraction:{ ...draft.extraction,color:e.target.value } })} /></label><label className="range-control">颜色容差<span><input aria-label="颜色容差" type="range" min="1" max="100" value={draft.extraction.tolerance} disabled={busy} onChange={e => change({ ...draft,extraction:{ ...draft.extraction,tolerance:Number(e.target.value) } })} /><output>{draft.extraction.tolerance}</output></span></label></>}
      <label className="range-control">去除小杂点<span><input aria-label="去除小杂点" type="range" min="0" max="1024" step="8" disabled={busy} value={draft.extraction.minimum_area} onChange={e => change({ ...draft,extraction:{ ...draft.extraction,minimum_area:Number(e.target.value) } })} /><output>{draft.extraction.minimum_area}</output></span></label><label className="checkbox-field"><input type="checkbox" disabled={busy} checked={draft.extraction.fill_holes} onChange={e => change({ ...draft,extraction:{ ...draft.extraction,fill_holes:e.target.checked } })} />填补内部孔洞</label><p className="tool-hint">剪纸的镂空通常需要保留；复杂纹理可结合框选和笔刷修正。</p><div className="form-field"><span>处理方式</span><Select label="处理方式" value={draft.profile} disabled={busy} onChange={value => change({ ...draft, profile: value })} options={[{value:'textile',label:'织绣纹理'},{value:'flat_color',label:'平面色彩图案'},{value:'silhouette',label:'剪影与剪纸'},{value:'artifact_photo',label:'器物照片'}]} /></div><button className="text-button" disabled={busy} onClick={() => change({ ...draft, box: null, strokes: [], feather: 0 })}>清除选区与笔触</button></details>
      <details className="provenance"><summary>来源记录</summary><p>{project.rights.creator}</p><p>许可：{project.rights.license}</p>{/^https?:\/\//.test(project.rights.source) ? <a href={project.rights.source} target="_blank" rel="noreferrer">查看来源<ArrowSquareOut size={14} /></a> : <p>{project.rights.source}</p>}<p className="source-name">{project.source_name}</p></details><p className="source-preserved"><Info size={18} weight="fill" />原始素材已保留</p>
    </aside>
  </div>;
}
