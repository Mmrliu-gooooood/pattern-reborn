import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, DownloadSimple, Sparkle, FrameCorners } from '@phosphor-icons/react';
import { api } from './api.js';
import { Brand, Ornament } from './components.jsx';
import { Select } from './Select.jsx';
import { Stages } from './Stages.jsx';
import { Settings } from './Settings.jsx';
import { VersionButton } from './ProjectTools.jsx';

const activeStates = ['queued','running','cancelling'];
const statusNames = {queued:'等待处理',running:'正在生成',cancelling:'等待结束并丢弃结果',succeeded:'生成完成',failed:'生成失败',stale:'项目已改变，结果未覆盖当前作品',cancelled:'任务已取消'};
const kindNames = {extracted:'提取纹样',extraction:'提取纹样',pattern:'重组作品',recomposition:'重组作品',generated:'AI 生成',generation:'AI 生成',mockup:'文创预览'};

export function Creative({ initial, back, notice, navigate }) {
  const [project,setProject] = useState(initial), [data,setData] = useState(null), [panel,setPanel] = useState('mockup');
  const [artwork,setArtwork] = useState(''), [template,setTemplate] = useState(''), [provider,setProvider] = useState(''), [size,setSize] = useState('');
  const [prompt,setPrompt] = useState(''), [negative,setNegative] = useState(''), [strength,setStrength] = useState('medium'), [application,setApplication] = useState('packaging');
  const [paid,setPaid] = useState(false), [job,setJob] = useState(null), [busy,setBusy] = useState(false), [error,setError] = useState(''), [settings,setSettings] = useState(false), [download,setDownload] = useState(null);
  const [analysis,setAnalysis] = useState(null), [showAnalysis,setShowAnalysis] = useState(false);
  const requestId = useRef(null), running = activeStates.includes(job?.status);
  const providers = data?.settings?.providers || data?.providers || [];
  const chosenProvider = providers.find(p => p.id === provider);
  const artworks = [...new Map([...(data?.references || []),...(data?.artworks || []),...(data?.mockups || [])].map(a => [a.id,a])).values()], chosen = artworks.find(a => a.id === artwork);
  async function load(selectNewest = false, applyDefault = false) {
    try {
      const value = await api(`/projects/${initial.id}/creative`); setData(value); setProject(value.project);
      setArtwork(previous => selectNewest ? value.mockups.at(-1)?.id || value.artworks.at(-1)?.id || previous : [...value.references,...value.artworks,...value.mockups].some(a => a.id === previous) ? previous : value.artworks.find(a => ['pattern','recomposition'].includes(a.kind))?.id || value.artworks[0]?.id || value.references[0]?.id || '');
      setTemplate(t => t || value.templates[0]?.id || '');
      const ps = value.settings?.providers || value.providers || [];
      const nextProvider = applyDefault || !provider ? value.settings?.default_provider || ps[0]?.id || '' : provider;
      const options = ps.find(p => p.id === nextProvider)?.size_options || [];
      setProvider(nextProvider); setSize(s => options.includes(s) ? s : options[0] || '');
      if (applyDefault) { setPaid(false); requestId.current = null; }
      const active = value.jobs?.find(j => activeStates.includes(j.status)); if (active) setJob(active);
      return value;
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [initial.id]);
  useEffect(() => {
    if (!job?.id || !running) return;
    let stopped = false, timer;
    const poll = async () => {
      try { const value = await api(`/projects/${project.id}/generation/jobs/${job.id}`); if (stopped) return; setJob(value.job); setProject(value.project); if (!activeStates.includes(value.job.status)) { await load(); notice(statusNames[value.job.status] || '任务已结束'); } else timer = setTimeout(poll,1500); }
      catch (e) { if (!stopped) { setError(e.message); timer = setTimeout(poll,4000); } }
    };
    timer = setTimeout(poll,1000); return () => { stopped = true; clearTimeout(timer); };
  }, [job?.id,running,project.id]);
  async function generate() {
    if (busy || running) return; setBusy(true); setError(''); setDownload(null);
    const fingerprint = JSON.stringify([project.revision,provider,chosenProvider?.settings_revision,prompt,size,strength,application,negative,artwork,chosenProvider?.stored_credential,paid]);
    const id = requestId.current?.fingerprint === fingerprint ? requestId.current.id : crypto.randomUUID(); requestId.current = {id,fingerprint};
    try { const value = await api(`/projects/${project.id}/generation`, {method:'POST',body:JSON.stringify({revision:project.revision,request_id:id,provider,settings_revision:chosenProvider?.settings_revision,prompt,size,structure_level:strength,target_application:application,negative_constraints:chosenProvider?.capabilities?.negative_constraints ? negative : '',colors:[],reference_id:artwork,mode:chosenProvider?.stored_credential ? 'byok' : 'platform',paid_confirmed:paid})}); setJob(value.job); requestId.current = null; setPaid(false); }
    catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  async function cancel() { try { const value = await api(`/projects/${project.id}/generation/jobs/${job.id}/cancel`,{method:'POST'}); setJob(value.job || value); } catch(e) { setError(e.message); } }
  async function mockup() {
    setBusy(true); setError(''); setDownload(null);
    try { await api(`/projects/${project.id}/mockups`,{method:'POST',body:JSON.stringify({revision:project.revision,template_id:template,artwork_id:artwork})}); await load(true); notice('文创预览已保存'); }
    catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  async function exportFile(format) {
    setBusy(true); setError('');
    try { const value = await api(`/projects/${project.id}/${chosen?.kind === 'extracted' ? 'exports' : 'creative/exports'}`,{method:'POST',body:JSON.stringify({revision:project.revision,...(chosen?.kind === 'extracted' ? {source:'result'} : {artwork_id:artwork}),format,include_original:false})}); setProject(value.project); setDownload(value.export); }
    catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  async function analyze() {
    setBusy(true); setError('');
    try { let value = await api(`/projects/${project.id}/analysis`); if (!value.analysis) value = await api(`/projects/${project.id}/analyze`,{method:'POST',body:JSON.stringify({revision:project.revision})}); setAnalysis(value.analysis); if (value.project) setProject(value.project); setShowAnalysis(true); }
    catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  function changeProvider(id) { setProvider(id); setSize(providers.find(p => p.id === id)?.size_options?.[0] || '1024x1024'); setPaid(false); requestId.current = null; }
  return <div className="editor-shell creative-shell"><div className="editor-brand"><Brand /></div><header className="editor-header"><button className="back-button" onClick={back}><ArrowLeft size={20} /><span>项目库</span></button><div className="editor-title"><h1>{project.name}</h1><span>灵感与应用</span></div><VersionButton project={project} disabled={busy || running} notice={notice} restored={value => navigate('creative',value)} /><button className="outline" onClick={() => setSettings(true)}>服务设置</button></header>
    <aside className="asset-rail"><h2>作品素材<span>{String(artworks.length).padStart(2,'0')}</span></h2>{artworks.map((a,index) => <button className={`asset ${artwork === a.id ? 'selected' : ''}`} key={a.id} onClick={() => {setArtwork(a.id);setDownload(null);requestId.current=null;}}><img src={a.url} alt="" /><span>{a.name || kindNames[a.kind] || '作品'} · {index+1}{a.ai_assisted ? ' · AI' : ''}</span></button>)}<Ornament /></aside>
    <main className="editing-region"><Stages stage="creative" change={stage => stage !== 'creative' && navigate(stage,project)} disabled={busy || running} /><div className="creative-mobile-source"><Select label="选择作品" value={artwork} onChange={setArtwork} options={artworks.map((a,index) => ({value:a.id,label:`${a.name || kindNames[a.kind] || '作品'} ${index+1}`}))} /></div>
      {error && <div className="error-message" role="alert">{error}<button onClick={() => setError('')}>关闭</button></div>}
      <div className="design-canvas">{chosen ? <img src={chosen.url} alt="当前作品预览" className="transparency" /> : <p className="tool-hint">正在读取作品…</p>}{busy && <div className="canvas-busy">正在处理…</div>}</div><div className="canvas-status"><span className="design-status">{chosen?.ai_assisted ? 'AI 辅助作品 · 来源已记录' : '本地作品 · 原始素材保留'}</span></div>
    </main>
    <aside className="inspector creative-inspector"><div className="inspector-tabs"><button aria-pressed={panel === 'mockup'} onClick={() => setPanel('mockup')}>文创预览</button><button aria-pressed={panel === 'generate'} onClick={() => setPanel('generate')}>生成灵感</button></div>
      {panel === 'mockup' ? <><p className="tool-hint">把保存的重组或生成作品放进应用场景，预览实际排布。若只有提取素材，请先进入重组并保存。</p><div className="form-field"><span>应用模板</span><Select label="应用模板" disabled={busy} value={template} onChange={setTemplate} options={(data?.templates || []).map(t => ({value:t.id,label:t.name}))} /></div>{data?.templates.find(t => t.id === template)?.url && <img className="template-preview" src={data.templates.find(t => t.id === template).url} alt="文创模板" />}<button className="primary full-width" disabled={busy || running || !template || !artwork || !['pattern','generation'].includes(chosen?.kind)} onClick={mockup}><FrameCorners size={18} />生成文创预览</button></> : <>
      <div className="form-field"><span>服务</span><Select label="生成服务" disabled={busy || running} value={provider} onChange={changeProvider} options={providers.map(p => ({value:p.id,label:p.name}))} /></div><p className="tool-hint">{chosenProvider?.available ? `模型：${chosenProvider.model}` : chosenProvider?.reason || '先在服务设置中配置密钥。'}</p>
      <label className="prompt-field">创作描述<textarea aria-label="创作描述" rows={4} maxLength={3000} value={prompt} disabled={busy || running} placeholder="描述希望保留的纹样特点、画面风格与用途" onChange={e => {setPrompt(e.target.value);requestId.current=null;}} /></label>
      <div className="form-field"><span>输出尺寸</span><Select label="生成尺寸" disabled={busy || running} value={size} onChange={setSize} options={(chosenProvider?.size_options || []).map(value => ({value,label:value}))} /></div>
      <div className="form-field"><span>结构保留</span><Select label="结构保留" disabled={busy || running} value={strength} onChange={setStrength} options={[{value:'high',label:'高 · 接近原作'},{value:'medium',label:'中 · 平衡变化'},{value:'low',label:'低 · 自由延展'}]} /></div>
      <div className="form-field"><span>目标应用</span><Select label="目标应用" disabled={busy || running} value={application} onChange={setApplication} options={[{value:'packaging',label:'包装'},{value:'bookmark',label:'书签'},{value:'textile',label:'织物'},{value:'poster',label:'海报'},{value:'phone_case',label:'手机壳'}]} /></div>
      {chosenProvider?.capabilities?.negative_constraints && <label className="prompt-field">避免出现<textarea rows={2} maxLength={1000} value={negative} disabled={busy || running} onChange={e => setNegative(e.target.value)} /></label>}
      <label className="checkbox-field paid-confirm"><input type="checkbox" checked={paid} disabled={busy || running} onChange={e => setPaid(e.target.checked)} />本次同意发送参考图与描述到该服务，并承担其可能收取的费用</label><button className="primary full-width" disabled={busy || running || !paid || !prompt.trim() || !chosenProvider?.available || !artwork || chosen?.kind === 'mockup'} onClick={generate}><Sparkle size={18} />{running ? '正在生成…' : job?.status === 'failed' ? '重新提交生成' : '开始生成'}</button>
      </>}
      {job && <section className="job-status" role="status"><strong>{statusNames[job.status] || job.status}</strong><p>{job.error || job.message || ''}</p>{running && <button className="text-button" onClick={cancel}>取消并丢弃结果</button>}</section>}
      <div className="creative-export"><h3>当前作品</h3><div className="settings-actions"><button className="outline" disabled={busy || running || !artwork} onClick={() => exportFile('png')}>导出 PNG</button><button className="outline" disabled={busy || running || !artwork} onClick={() => exportFile('zip')}>导出来源包</button></div>{download && <a className="download-link" href={download.url} download><DownloadSimple size={18} />下载 {download.format.toUpperCase()}</a>}</div>
      <button className="text-button" disabled={busy || running} onClick={analyze}>查看纹样分析</button>{showAnalysis && <Analysis data={analysis} />}
    </aside>{settings && <Settings close={() => {setSettings(false);load(false,true);}} />}
  </div>;
}

function Analysis({ data }) {
  if (!data) return <p className="tool-hint">尚无分析结果。</p>;
  const percentage = value => typeof value === 'number' ? `${Math.round(value * 100)}%` : '—';
  return <section className="analysis-summary"><h3>主色与结构</h3><div className="analysis-colors">{(data.palette || []).map((c,index) => { const color = c.hex || c.hex_value || (c.rgb ? `rgb(${c.rgb.join(',')})` : '#77846A'); const match = data.color_matches?.find(m => m.hex_value === c.hex_value); return <span key={index}><i style={{background:color}} />{match?.traditional_name_zh || color}<small>{percentage(c.coverage)}</small></span>; })}</div>
    {data.contours && <p className="tool-hint">外轮廓 {data.contours.contour_count} 处 · 镂空 {data.contours.hole_count} 处<br />纹样覆盖 {percentage(data.contours.foreground_ratio)}</p>}
    {data.symmetry && <p className="tool-hint">垂直对称度 {percentage(data.symmetry.vertical_score)}<br />水平对称度 {percentage(data.symmetry.horizontal_score)}<br />{data.symmetry.rotations?.map(r => `${r.order} 重旋转 ${percentage(r.score)}`).join(' · ')}</p>}
    <p className="tool-hint">分析基于已保存的提取纹样；传统色名称为色值近似匹配，不代表历史颜料鉴定。</p></section>;
}
