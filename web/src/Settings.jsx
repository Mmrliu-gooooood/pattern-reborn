import { useConfirm } from './useConfirm.jsx';
import { useEffect, useState } from 'react';
import { api } from './api.js';
import { Modal } from './components.jsx';
import { Select } from './Select.jsx';

export function Settings({ close }) {
  const [data, setData] = useState(null), [provider, setProvider] = useState('seedream'), [key, setKey] = useState('');
  const [endpoint, setEndpoint] = useState(''), [model, setModel] = useState(''), [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const [protocol,setProtocol] = useState('openai_images_edits'), [sizes,setSizes] = useState(''), [models,setModels] = useState([]), [search,setSearch] = useState('');
  function choose(id, config = data) { const p = config?.providers.find(item => item.id === id); setProvider(id); setEndpoint(p?.base_url || ''); setModel(p?.model || ''); setProtocol(p?.protocol || 'openai_images_edits'); setSizes((p?.size_options || []).join(', ')); setKey(''); setMessage(''); }
  async function load() { try { const result = await api('/settings'); setData(result); choose(result.default_provider || 'seedream',result); } catch (e) { setMessage(e.message); } }
  useEffect(() => { load(); }, []);
  async function save(clearKey = false) {
    setBusy(true); setMessage('');
    const change = clearKey ? {provider,api_key:''} : {provider,default_provider:provider,base_url:endpoint,model,protocol,size_options:sizes.split(/[,，\s]+/).filter(Boolean),...(key.trim() ? {api_key:key.trim()} : {})};
    try { const result = await api('/settings', { method:'PUT',body:JSON.stringify(change) }); setData(result); setKey(''); setMessage(clearKey ? '本机密钥已清除' : '已保存为默认生成服务，重启后仍可使用'); }
    catch (e) { setMessage(e.message); } finally { setBusy(false); }
  }
  async function refreshModels() {
    setBusy(true); setMessage('');
    try { const result = await api('/providers/openrouter/models'); setModels(result.models); setMessage(`已读取 ${result.models.length} 个支持参考图的图像模型`); }
    catch(e) { setMessage(e.message); } finally { setBusy(false); }
  }
  function chooseModel(id) { setModel(id); const item = models.find(m => m.id === id); if (item?.size_options?.length) setSizes(item.size_options.join(', ')); }
  const selected = data?.providers.find(p => p.id === provider);
  const generic = provider === 'custom', router = provider === 'openrouter';
  const filteredModels = models.filter(m => `${m.name} ${m.id}`.toLowerCase().includes(search.toLowerCase()));
  return <Modal title="工作台设置" close={() => !busy && close()}><div className="settings-copy"><p>基础创作在本机完成。AI 生成会向所选服务发送参考图与提示词，并可能产生费用。</p></div>
    {data?.config_error && <p className="error-message" role="alert">{data.config_error}</p>}
    {data?.providers.length ? <form className="project-form" onSubmit={e => { e.preventDefault(); save(); }}>
      <div className="form-field"><span>默认生成服务</span><Select label="默认生成服务" value={provider} disabled={busy} onChange={choose} options={data.providers.map(p => ({value:p.id,label:p.name}))} /></div>
      {generic && <div className="form-field"><span>接口协议</span><Select label="接口协议" value={protocol} disabled={busy} onChange={setProtocol} options={[{value:'openai_images_edits',label:'OpenAI Images Edits · 文件上传'},{value:'images_generations_json',label:'Images Generations · JSON 参考图'},{value:'openrouter_images',label:'OpenRouter Images · JSON 参考图'}]} /></div>}
      <label>{generic || router ? '完整请求地址' : '服务地址'}<input type="url" required value={endpoint} disabled={busy} onChange={e => setEndpoint(e.target.value)} /></label>
      {(generic || router) && <p className="tool-hint">{router ? 'OpenRouter 图像接口使用 /api/v1/images，可在多个图像模型间切换。' : '填写服务文档中的完整 HTTPS 请求地址；应用按所选协议发送一张参考图，不会自动补全地址。'} 更换地址后请重新填写对应密钥。</p>}
      {router && <><button type="button" className="outline" disabled={busy} onClick={refreshModels}>读取 OpenRouter 图像模型</button><p className="tool-hint">只读取官方公开目录，无需密钥，不发送作品或发起生成。离线时可手动输入模型 ID。</p>{models.length > 0 && <><label>搜索图像模型<input value={search} disabled={busy} placeholder="按名称或 ID 搜索" onChange={e => setSearch(e.target.value)} /></label>{filteredModels.length ? <Select label="图像模型目录" value={model} disabled={busy} onChange={chooseModel} options={filteredModels.map(m => ({value:m.id,label:m.name}))} /> : <p className="tool-hint">没有匹配的图像模型。</p>}</>}</>}
      <label>模型名称 / ID<input required value={model} disabled={busy} onChange={e => setModel(e.target.value)} /></label>
      <label>输出尺寸（用逗号分隔）<input required value={sizes} disabled={busy} placeholder="1024x1024, 2K" onChange={e => setSizes(e.target.value)} /></label>
      <label>本机 API Key<input autoComplete="off" type="password" value={key} disabled={busy} placeholder={selected?.stored_credential ? '已保存；留空保持' : '保存后重启仍可使用'} onChange={e => setKey(e.target.value)} /></label>
      <p className="tool-hint">{selected?.stored_credential ? '本机密钥已保存。' : selected?.platform_credential ? '已检测到本地环境配置密钥。' : '尚未配置密钥。'} 密钥由 Windows 当前用户加密，不回显、不写入浏览器存储或项目备份。留空保留原密钥；点击清除按钮删除。</p>
      <div className="settings-actions"><button className="primary" disabled={busy}>保存设置</button><button type="button" className="outline" disabled={busy || !selected?.stored_credential} onClick={() => save(true)}>清除本机密钥</button></div>
      <details><summary>运行状态与帮助</summary><ul className="setup-list">{Object.entries(data.capabilities || {}).map(([name,value]) => <li key={name}>{name}：{typeof value === 'boolean' ? value ? '可用' : '未安装' : value?.available ? '可用' : value?.reason || '未配置'}</li>)}</ul><p className="tool-hint">完整项目备份可从项目菜单下载；项目库的「导入备份」可恢复为独立项目。提取、重组与配色都有草稿和版本记录。</p><a href="/api/help" target="_blank" rel="noreferrer">打开本地使用手册</a></details>
    </form> : <button className="outline" onClick={load}>重试读取设置</button>}{message && <p className="form-note" role="status">{message}</p>}<Recovery />
  </Modal>;
}

function Recovery() {
  const [confirm, confirmation] = useConfirm();
  const [items,setItems] = useState([]), [selected,setSelected] = useState({}), [busy,setBusy] = useState(false), [message,setMessage] = useState('');
  async function inspect() { try { setItems((await api('/recovery')).projects); } catch(e) {setMessage(e.message);} }
  useEffect(() => { inspect(); },[]);
  async function recover(item) {
    if (!await confirm(`从历史记录恢复「${item.name}」？损坏的项目记录会另外保留。`)) return;
    setBusy(true);
    try { await api(`/projects/${item.id}/recover`,{method:'POST',body:JSON.stringify({version_id:selected[item.id] || item.versions[0].id})}); setMessage('项目已恢复，关闭设置后可在项目库打开。'); await inspect(); }
    catch(e) {setMessage(e.message);} finally {setBusy(false);}
  }
  return <section className="recovery-panel">{confirmation}<h3>项目恢复检查</h3><p className="tool-hint">{items.length ? '发现打不开的项目，可尝试恢复有效历史版本。' : '未发现可从历史恢复的损坏项目。'}</p>{items.map(item => <article key={item.id}><strong>{item.name}</strong><Select label={`${item.name}的恢复版本`} value={selected[item.id] || item.versions[0].id} onChange={value => setSelected({...selected,[item.id]:value})} options={item.versions.map(v => ({value:v.id,label:`${v.name} · ${new Date(v.created_at).toLocaleString('zh-CN')}`}))} /><button className="outline" disabled={busy} onClick={() => recover(item)}>恢复项目</button></article>)}{message && <p className="tool-hint" role="status">{message}</p>}</section>;
}
