import { Selection, Palette, Package, Sparkle } from '@phosphor-icons/react';

export function Stages({ stage, change, disabled = false, ready = true }) {
  return <nav className="workspace-stages" aria-label="创作步骤">{[['extract', '提取', Selection], ['design', '重组与配色', Palette], ['creative', '灵感与应用', Sparkle], ['export', '导出', Package]].map(([id, title, Icon], index) => <button key={id} aria-current={stage === id ? 'step' : undefined} disabled={disabled || (!ready && id !== 'extract')} onClick={() => change(id)}><Icon size={17} /><span>{title}</span><small>0{index + 1}</small></button>)}</nav>;
}

