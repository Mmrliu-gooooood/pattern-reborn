import { useConfirm } from './useConfirm.jsx';
import { useEffect, useState } from 'react';
import { api } from './api.js';
import { Modal } from './components.jsx';
import { Select } from './Select.jsx';

export function Settings({ close }) {
  const [data, setData] = useState(null), [provider, setProvider] = useState('seedream'), [key, setKey] = useState('');
  const [endpoint, setEndpoint] = useState(''), [model, setModel] = useState(''), [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  function choose(id, config = data) { const p = config?.providers.find(item => item.id === id); setProvider(id); setEndpoint(p?.base_url || ''); setModel(p?.model || ''); setKey(''); }
  async function load() { try { const result = await api('/settings'); setData(result); choose(provider,result); } catch (e) { setMessage(e.message); } }
  useEffect(() => { load(); }, []);
  async function save(clearKey = false) {
    setBusy(true); setMessage('');
    try { const result = await api('/settings', { method:'PUT',body:JSON.stringify({ provider,base_url:endpoint,model,...(clearKey ? {api_key:''} : key ? {api_key:key} : {}) }) }); setData(result); setKey(''); setMessage(clearKey ? '会话密钥已清除' : '设置已更新'); }
    catch (e) { setMessage(e.message); } finally { setBusy(false); }
  }
  const selected = data?.providers.find(p => p.id === provider);
  return <Modal title="工作台设置" close={() => !busy && close()}><div className="settings-copy"><p>基础创作在本机完成。AI 生成会向所选服务发送参考图与提示词，并可能产生费用。</p></div>
    {data ? <form className="project-form" onSubmit={e => { e.preventDefault(); save(); }}>
      <div className="form-field"><span>生成服务</span><Select label="生成服务" value={provider} disabled={busy} onChange={choose} options={data.providers.map(p => ({value:p.id,label:p.name}))} /></div>
      <label>服务地址<input type="url" required value={endpoint} disabled={busy} onChange={e => setEndpoint(e.target.value)} /></label><label>模型名称<input required value={model} disabled={busy} onChange={e => setModel(e.target.value)} /></label>
      <label>本次会话 API Key<input autoComplete="off" type="password" value={key} disabled={busy} placeholder={selected?.session_credential ? '已设置；留空保持' : '不会写入项目或备份'} onChange={e => setKey(e.target.value)} /></label>
      <p className="tool-hint">{selected?.session_credential ? '本次浏览器会话密钥已设置。' : selected?.platform_credential ? '已检测到本地环境配置密钥。' : '尚未配置密钥。'} 密钥不回显、不写入浏览器存储，重启服务后会话配置失效。</p>
      <div className="settings-actions"><button className="primary" disabled={busy}>保存设置</button><button type="button" className="outline" disabled={busy || !selected?.session_credential} onClick={() => save(true)}>清除会话密钥</button></div>
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
