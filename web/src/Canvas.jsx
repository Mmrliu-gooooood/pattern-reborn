import { useEffect, useRef, useState } from 'react';
import { imagePoint, orderedBox } from './history.js';

export function EditorCanvas({ project, draft, onChange, tool, brush, zoom, pan, setPan, view, image, busy, processing = busy }) {
  const container = useRef(null), canvas = useRef(null), gesture = useRef(null);
  const [size, setSize] = useState({ width: 800, height: 600 });
  const [live, setLive] = useState(null);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setSize(entry.contentRect));
    observer.observe(container.current); return () => observer.disconnect();
  }, []);
  const fit = Math.max(0.01, Math.min((size.width - 48) / project.width, (size.height - 48) / project.height));
  const scale = fit * zoom;
  useEffect(() => {
    const ctx = canvas.current.getContext('2d');
    ctx.clearRect(0, 0, project.width, project.height);
    if (view !== 'source') return;
    const strokes = live?.mode ? [...draft.strokes, live] : draft.strokes;
    strokes.forEach(stroke => {
      ctx.strokeStyle = stroke.mode === 'keep' ? '#6bd6a6a0' : '#e98c70aa'; ctx.fillStyle = ctx.strokeStyle;
      ctx.lineWidth = stroke.width; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.beginPath();
      stroke.points.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
      if (stroke.points.length === 1) { ctx.arc(...stroke.points[0], stroke.width / 2, 0, Math.PI * 2); ctx.fill(); } else ctx.stroke();
    });
    const box = live?.box || draft.box;
    if (box) { ctx.setLineDash([8 / scale, 5 / scale]); ctx.lineWidth = 1.5 / scale; ctx.strokeStyle = '#f4dca2'; ctx.strokeRect(box[0], box[1], box[2] - box[0], box[3] - box[1]); ctx.setLineDash([]); }
  }, [draft, live, view, project.width, project.height, scale]);
  function start(event) {
    if (busy || event.button !== 0 || (view !== 'source' && tool !== 'hand')) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = imagePoint(event.clientX, event.clientY, canvas.current.getBoundingClientRect(), project.width, project.height);
    if (tool === 'hand') gesture.current = { x: event.clientX, y: event.clientY, pan };
    else if (tool === 'box') { gesture.current = { first: point }; setLive({ box: [...point, ...point] }); }
    else if (draft.strokes.length < 100) { gesture.current = { stroke: { mode: tool, width: brush, points: [point] } }; setLive(gesture.current.stroke); }
  }
  function move(event) {
    const g = gesture.current; if (!g) return;
    if (g.pan) return setPan({ x: g.pan.x + event.clientX - g.x, y: g.pan.y + event.clientY - g.y });
    const point = imagePoint(event.clientX, event.clientY, canvas.current.getBoundingClientRect(), project.width, project.height);
    if (g.first) setLive({ box: orderedBox(g.first, point) });
    else if (g.stroke.points.length < 3000) { g.stroke = { ...g.stroke, points: [...g.stroke.points, point] }; setLive(g.stroke); }
  }
  function end() {
    if (gesture.current && live) {
      if (live.box && live.box[2] > live.box[0] && live.box[3] > live.box[1]) onChange({ ...draft, box: live.box });
      if (live.mode) onChange({ ...draft, strokes: [...draft.strokes, live] });
    }
    gesture.current = null; setLive(null);
  }
  return <div className={`canvas-stage tool-${tool}`} ref={container}>
    <div className="image-plane" style={{ width: project.width * scale, height: project.height * scale, left: size.width / 2 + pan.x, top: size.height / 2 + pan.y }}>
      <img src={image} alt={view === 'source' ? project.name + '原始图像' : view === 'mask' ? '提取蒙版预览' : '提取结果预览'} draggable="false" />
      <canvas ref={canvas} width={project.width} height={project.height} aria-label="纹样编辑画布，可拖动框选或绘制保留与去除笔触" onPointerDown={start} onPointerMove={move} onPointerUp={end} onPointerCancel={() => { gesture.current = null; setLive(null); }} />
    </div>
    {processing && <div className="canvas-busy" role="status">正在处理纹样…</div>}
  </div>;
}
