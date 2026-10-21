import { useConfirm } from './useConfirm.jsx';
import { useEffect, useReducer, useState } from 'react';
import { ArrowLeft, ArrowRight, DownloadSimple, FloppyDisk, SquaresFour, ArrowsHorizontal, CircleDashed, FrameCorners, FlipHorizontal, ArrowsClockwise, Palette, Selection, Package } from '@phosphor-icons/react';
import { api } from './api.js';
import { Brand, Ornament } from './components.jsx';
import { Editor } from './Editor.jsx';
import { Select } from './Select.jsx';
import { Stages } from './Stages.jsx';
import { historyReducer, initialHistory } from './history.js';
import { useDraft } from './useDraft.js';
import { DraftNotice, VersionButton } from './ProjectTools.jsx';
import { Creative } from './Creative.jsx';

const layouts = [['two_way', '二方连续', ArrowsHorizontal], ['four_way', '四方连续', SquaresFour], ['mirror', '镜像对称', FlipHorizontal], ['rotation', '旋转组合', ArrowsClockwise], ['radial', '放射团花', CircleDashed], ['border', '边框纹饰', FrameCorners]];
const palettes = [ ['朱砂 · 绢白', ['#A4382B', '#C87546', '#E1B979', '#F4EAD6', '#67705A', '#303F35']], ['青花 · 月白', ['#173E66', '#37688C', '#7B9BA9', '#E9E8D9', '#B6C2BE', '#F4F0E4']], ['黛绿 · 泥金', ['#254A3C', '#59725A', '#A99458', '#D5BF86', '#E5DCC6', '#434B3B']] ];

export function Workspace({ initial, back, notice }) {
  const [project, setProject] = useState(initial), [stage, setStage] = useState('extract');
  function navigate(value, updated) { if (updated) setProject(updated); setStage(value); }
  return stage === 'creative' ? <Creative key={project.revision} initial={project} back={back} notice={notice} navigate={navigate} /> : stage === 'extract' ? <Editor key={project.revision} initial={project} back={back} notice={notice} navigate={navigate} /> : <Composer key={project.revision} initial={project} initialStage={stage} back={back} notice={notice} navigate={navigate} />;
}

function Composer({ initial, initialStage, back, notice, navigate }) {
  const [confirm, confirmation] = useConfirm();
  const [project, setProject] = useState(initial), [stage, setStage] = useState(initialStage);
  const [context, setContext] = useState(null), [saved, setSaved] = useState('');
  const [history, dispatch] = useReducer(historyReducer, null, initialHistory);
  const settings = history.present;
  const setSettings = value => dispatch({type:'reset',value});
  const [preview, setPreview] = useState(null), [previewSettings, setPreviewSettings] = useState('');
  const [working, setBusy] = useState(false), [error, setError] = useState(''), [panel, setPanel] = useState('layout');
  const [exportSource, setExportSource] = useState(initial.has_pattern ? 'pattern' : 'result'), [format, setFormat] = useState('png'), [includeOriginal, setIncludeOriginal] = useState(false);
  const [latest, setLatest] = useState(null);
  const serialized = JSON.stringify(settings), dirty = settings !== null && serialized !== saved;
  const draftStore = useDraft({ project,kind:'design',value:settings,dirty,busy:working,restore:value => dispatch({type:'set',value}) });
  const busy = working || !draftStore.ready || Boolean(draftStore.pending) || draftStore.clearing;
  useEffect(() => { const key = e => { if (stage !== 'design' || busy || !(e.ctrlKey || e.metaKey) || ['INPUT','TEXTAREA'].includes(e.target.tagName)) return; if (['z','y'].includes(e.key.toLowerCase())) { e.preventDefault(); dispatch({type:e.key.toLowerCase() === 'y' || e.shiftKey ? 'redo' : 'undo'}); } }; window.addEventListener('keydown',key); return () => window.removeEventListener('keydown',key); },[stage,busy]);
  async function load() {
    setError('');
    try {
      const value = await api(`/projects/${initial.id}/design`);
      setContext(value); setSettings(value.settings); setSaved(JSON.stringify(value.settings)); setProject(value.project);
      setPreview(value.project.pattern_url); setPreviewSettings(value.project.has_pattern ? JSON.stringify(value.settings) : '');
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [initial.id]);
  useEffect(() => { const guard = e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [dirty]);
  async function leave(destination) {
    if (busy || (dirty && !await confirm('还有未保存为版本的构图或配色，已自动保存的草稿可下次恢复。继续吗？'))) return;
    if (destination === 'library') back(); else navigate(destination, project);
  }
  function changeStage(value) {
    if (value === 'extract' || value === 'creative') leave(value);
    else if (value === 'export' && dirty) setError('请先保存当前作品，再导出。');
    else { setError(''); setStage(value); }
  }
  function update(values) { dispatch({type:'set',value:{ ...settings,...values }}); setLatest(null); }
  async function render(save) {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const value = await api(`/projects/${project.id}/design/${save ? 'save' : 'preview'}`, { method: 'POST', body: JSON.stringify({ revision: project.revision, settings }) });
      if (save) { await draftStore.clear(); setProject(value); setSaved(serialized); setPreview(value.pattern_url); setExportSource('pattern'); notice(value.warnings?.length ? value.warnings.join('；') : '构图与配色已保存'); }
      else setPreview(value.image);
      setPreviewSettings(serialized);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function exportFile() {
    setBusy(true); setError(''); setLatest(null);
    try {
      const value = await api(`/projects/${project.id}/exports`, { method: 'POST', body: JSON.stringify({ revision: project.revision, source: exportSource, format, include_original: includeOriginal }) });
      setProject(value.project); setLatest(value.export); setContext(c => ({ ...c, exports: [value.export, ...c.exports] })); notice(value.project.warnings?.length ? value.project.warnings.join('；') : '文件已准备好，可以下载');
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  const shown = stage === 'export' ? (exportSource === 'pattern' ? project.pattern_url : project.result_url) : preview;
  return <div className="editor-shell composer-shell">{confirmation}<div className="editor-brand"><Brand /></div>
    <header className="editor-header"><button className="back-button" disabled={busy} onClick={() => leave('library')}><ArrowLeft size={20} /><span>项目库</span></button><div className="editor-title"><h1>{project.name}</h1><span className={dirty ? 'unsaved' : ''}>{dirty ? '有未保存修改' : project.has_pattern ? '作品已保存' : '开始创作'}</span></div><VersionButton project={project} disabled={busy} notice={notice} restored={async value => { await draftStore.clear(); navigate('design',value); }} /><button className="primary" disabled={busy || !settings || stage === 'export'} onClick={() => render(true)}><FloppyDisk size={19} /><span>{working ? '处理中…' : '保存作品'}</span></button></header>
    <aside className="asset-rail"><h2>创作素材<span>01</span></h2><div className="asset selected"><img src={project.result_url} alt="已提取的纹样" /><span>提取纹样</span></div><p className="tool-hint">以原作纹样为单元，延展新的构图与色彩。</p><Ornament /><p className="asset-note">取其形<br />续其意</p></aside>
    <main className="editing-region"><Stages stage={stage} change={changeStage} disabled={busy} />{settings && <DraftNotice draft={draftStore} />}
      {error && <div className="error-message" role="alert">{error}{!context && <button onClick={load}>重试</button>}<button onClick={() => setError('')}>关闭</button></div>}
      <div className="design-canvas" aria-busy={busy}>{shown ? <img className="transparency" src={shown} alt={stage === 'export' ? '导出内容预览' : '重组作品预览'} /> : <div className="design-empty"><img src={project.result_url} alt="纹样单元" /><h2>让一枚纹样，生出新的秩序</h2><p>选择构图与色彩，预览你的第一件作品。</p><button className="primary" disabled={busy || !settings} onClick={() => render(false)}>生成预览<ArrowRight size={18} /></button></div>}{working && <div className="canvas-busy">{stage === 'export' ? '正在准备导出…' : '正在铺陈纹样…'}</div>}</div>
      <div className="canvas-status"><span className="design-status">{stage === 'design' && preview && serialized !== previewSettings ? '参数已更改 · 请更新预览' : stage === 'export' ? '导出已保存的版本' : settings?.background ? '实色背景' : '透明背景'}</span><span>{stage === 'export' && exportSource === 'result' ? `${project.width} × ${project.height}` : settings && `${settings.width} × ${settings.height}`} px</span></div>
    </main>
    <aside className="inspector design-inspector">{!settings ? <p className="tool-hint">{error ? '暂时无法加载创作设置。' : '正在读取纹样与色彩…'}</p> : stage === 'export' ? <>
      <h2>导出作品</h2><p className="tool-hint">为作品留一份清晰的底稿。</p>
      <div className="form-field"><span>导出内容</span><Select label="导出内容" disabled={busy} value={exportSource} onChange={value => { setExportSource(value); setLatest(null); }} options={[{ value:'result', label:'提取纹样' }, ...(project.has_pattern ? [{ value:'pattern', label:'重组作品' }] : [])]} /></div>
      <div className="format-options">{[['png', 'PNG 图像', '保留透明度，适合排版与分享'], ['svg', 'SVG 矢量', '描摹轮廓，便于后续矢量编辑'], ['zip', '作品包 ZIP', '图像、参数与来源记录']].map(([id, title, desc]) => <button key={id} disabled={busy || (id === 'svg' && !context.svg_available)} aria-pressed={format === id} className={format === id ? 'selected' : ''} onClick={() => { setFormat(id); setLatest(null); }}><strong>{title}</strong><span>{desc}</span></button>)}</div>
      {!context.svg_available && <p className="tool-hint">{context.svg_reason}</p>}{format === 'svg' && <p className="tool-hint">矢量描摹会简化织物纹理；照片类纹样建议同时保留 PNG。</p>}
      {format === 'zip' && <label className="checkbox-field"><input type="checkbox" disabled={busy} checked={includeOriginal} onChange={e => { setIncludeOriginal(e.target.checked); setLatest(null); }} />包含原始素材</label>}
      <button className="primary full-width" disabled={busy} onClick={exportFile}><Package size={19} />{busy ? '正在准备…' : '准备导出文件'}</button>
      {latest && <a className="download-link" href={latest.url} download><DownloadSimple size={18} />下载 {latest.format.toUpperCase()}</a>}
      {!!context.exports.length && <section className="export-history"><h3>导出记录</h3><p className="tool-hint">每条记录保留当时保存的版本。</p>{context.exports.slice(0, 8).map(item => <a key={item.id} href={item.url} download><span>{({pattern:'重组作品',result:'提取纹样',generation:'生成作品',mockup:'文创预览'})[item.source] || '作品'} · {item.format.toUpperCase()}<small>{new Date(item.created_at).toLocaleString('zh-CN')}</small></span><DownloadSimple size={16} /></a>)}</section>}
    </> : <>
      <div className="design-controls"><div className="inspector-tabs"><button aria-pressed={panel === 'layout'} onClick={() => setPanel('layout')}>纹样重组</button><button aria-pressed={panel === 'color'} onClick={() => setPanel('color')}>配色</button></div>
      <fieldset disabled={busy} className="design-fields">{panel === 'layout' ? <>
        <p className="eyebrow">构图方式</p><div className="layout-options">{layouts.map(([id, title, Icon]) => <button key={id} aria-pressed={settings.layout === id} onClick={() => update({ layout:id })}><Icon size={23} /><span>{title}</span></button>)}</div>
        <div className="dimension-fields"><label>画布宽度<input type="number" min="64" max="4096" value={settings.width} onChange={e => update({ width:Number(e.target.value) })} /></label><label>画布高度<input type="number" min="64" max="4096" value={settings.height} onChange={e => update({ height:Number(e.target.value) })} /></label></div>
        <div className="size-presets">{[[1024,1024,'方形'],[1440,960,'横幅'],[960,1440,'竖幅']].map(([width,height,label]) => <button key={label} onClick={() => update({ width,height })}>{label}</button>)}</div>
        {[['scale','纹样大小',5,100,Math.round(settings.scale*100),'%'],['spacing','单元间距',0,256,settings.spacing,'px'],['angle','单元角度',-180,180,settings.angle,'°']].map(([key,title,min,max,value,unit]) => <label className="range-control" key={key}>{title}<span><input aria-label={title} type="range" min={min} max={max} value={value} onChange={e => update({ [key]:Number(e.target.value)/(key==='scale'?100:1) })} /><output>{value}{unit}</output></span></label>)}
        {['rotation','radial'].includes(settings.layout) && <div className="form-field"><label htmlFor="design-seed">构图种子</label><input id="design-seed" type="number" min="0" max="2147483647" value={settings.seed} onChange={e => update({ seed:Number(e.target.value) })} /></div>}
      </> : <>
        <p className="eyebrow">色彩灵感</p><div className="palette-presets">{palettes.map(([name, colors]) => <button key={name} onClick={() => update({ colors:Object.fromEntries(context.palette.map((source,index) => [source, colors[index]])) })}><span>{colors.map(color => <i key={color} style={{ background:color }} />)}</span><small>{name}</small></button>)}</div>
        <div className="palette-heading"><h3>纹样色彩</h3><button className="text-button" onClick={() => update({ colors:{} })}>还原原色</button></div>
        <p className="tool-hint">替换主色，同时保留纹理与明暗。</p><div className="color-rows">{context.palette.map((source,index) => <label key={source}><i style={{ background:source }} title={source} /><ArrowRight size={14} /><input aria-label={`纹样颜色 ${index+1}`} type="color" value={settings.colors[source] || source} onChange={e => update({ colors:{ ...settings.colors,[source]:e.target.value } })} /><span>{(settings.colors[source] || source).toUpperCase()}</span></label>)}</div>
      </>}
      <section className="background-controls"><label className="checkbox-field"><input type="checkbox" checked={settings.background === null} onChange={e => update({ background:e.target.checked ? null : '#F4EFDF' })} />透明背景</label>{settings.background !== null && <label className="background-color">画布底色<input aria-label="画布底色" type="color" value={settings.background} onChange={e => update({ background:e.target.value })} /></label>}</section>
      </fieldset></div><div className="design-actions"><div className="history-controls"><button disabled={busy || !history.past.length} onClick={() => dispatch({type:'undo'})}>撤销</button><button disabled={busy || !history.future.length} onClick={() => dispatch({type:'redo'})}>重做</button></div><button className="outline preview-button" disabled={busy} onClick={() => render(false)}>{working ? '处理中…' : '更新预览'}</button><button className="text-button next-stage" disabled={busy || dirty || !project.has_pattern} onClick={() => changeStage('export')}>前往导出<ArrowRight size={16} /></button></div>
    </>}</aside>
  </div>;
}
