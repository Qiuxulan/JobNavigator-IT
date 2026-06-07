from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.career_catalog import load_resources, load_roles, load_skill_graph, role_top_skills
from app.services.extractor import ExtractorService
from app.services.graph_path_planner_v2 import GraphPathPlannerV2

ROOT = Path(__file__).parents[2]
REPORT_DIR = ROOT / "reports"

COLORS = {
    "job": "#df6f52",
    "skill": "#e8b7bf",
    "resource": "#f1d4d9",
    "overlap": "#cf8e9d",
    "missing": "#d96a57",
    "prereq": "#cfc8c6",
    "path": "#c98590",
}


def _node_key(node_type: str, node_id: str) -> str:
    return f"{node_type}:{node_id}"


def _build_html(title: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      height: 100%;
      background: #f6f0ea;
      color: #6a5752;
      font-family: "Palatino Linotype", "Book Antiqua", "STKaiti", "KaiTi", serif;
      overflow: hidden;
    }}
    #app {{
      display: grid;
      grid-template-columns: 1fr 340px;
      height: 100%;
    }}
    #stage {{
      position: relative;
      background:
        radial-gradient(circle at 18% 18%, rgba(231, 145, 114, .18), transparent 30%),
        radial-gradient(circle at 82% 12%, rgba(232, 183, 191, .20), transparent 26%),
        radial-gradient(circle at 70% 70%, rgba(208, 201, 198, .18), transparent 28%),
        linear-gradient(180deg, #faf6f2, #f2ece6);
    }}
    canvas {{
      display: block;
      width: 100%;
      height: 100%;
      cursor: grab;
    }}
    canvas.dragging {{
      cursor: grabbing;
    }}
    #toolbar {{
      position: absolute;
      top: 16px;
      left: 16px;
      display: flex;
      gap: 8px;
      z-index: 10;
    }}
    .btn {{
      border: 1px solid rgba(178, 154, 147, .35);
      background: rgba(255, 249, 244, .86);
      color: #7c5f58;
      padding: 8px 12px;
      border-radius: 14px;
      font-size: 13px;
      cursor: pointer;
      backdrop-filter: blur(10px);
      box-shadow: 0 8px 24px rgba(163, 143, 137, .10);
    }}
    .btn:hover {{
      background: rgba(255, 245, 241, .98);
    }}
    #sidebar {{
      border-left: 1px solid rgba(202, 191, 186, .55);
      background: rgba(252, 247, 241, .96);
      padding: 18px 16px;
      overflow: auto;
      box-shadow: -8px 0 24px rgba(172, 161, 155, .08);
    }}
    h1 {{
      font-size: 20px;
      margin: 0 0 12px;
      color: #b05f49;
      letter-spacing: .4px;
    }}
    h2 {{
      font-size: 14px;
      margin: 18px 0 8px;
      color: #b56d72;
    }}
    .meta, .legend-item, .detail-row {{
      font-size: 13px;
      line-height: 1.5;
      color: #746661;
    }}
    .pill {{
      display: inline-block;
      padding: 2px 8px;
      margin: 0 6px 6px 0;
      border-radius: 999px;
      font-size: 12px;
      background: rgba(247, 231, 233, .95);
      color: #8b5f59;
      border: 1px solid rgba(209, 187, 182, .30);
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 6px 0;
    }}
    .swatch {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
      flex: 0 0 auto;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: rgba(255, 250, 247, .96);
      border: 1px solid rgba(209, 197, 192, .45);
      border-radius: 12px;
      padding: 10px;
      font-size: 12px;
      color: #6d5a55;
    }}
  </style>
</head>
<body>
  <div id="app">
    <div id="stage">
      <div id="toolbar">
        <button class="btn" id="fitBtn">适配视图</button>
        <button class="btn" id="toggleLabelsBtn">隐藏标签</button>
      </div>
      <canvas id="canvas"></canvas>
    </div>
    <aside id="sidebar">
      <h1>{title}</h1>
      <div class="meta" id="summary"></div>
      <h2>图例</h2>
      <div id="legend"></div>
      <h2>节点详情</h2>
      <div id="details" class="meta">点击节点查看详情</div>
    </aside>
  </div>
  <script>
    const GRAPH = {payload};
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const summary = document.getElementById('summary');
    const details = document.getElementById('details');
    const legend = document.getElementById('legend');
    const fitBtn = document.getElementById('fitBtn');
    const toggleLabelsBtn = document.getElementById('toggleLabelsBtn');

    let width = 0;
    let height = 0;
    let scale = 1;
    let offsetX = 0;
    let offsetY = 0;
    let draggingNode = null;
    let panning = false;
    let lastX = 0;
    let lastY = 0;
    let showLabels = true;
    let physicsRunning = true;
    let hoveredNode = null;
    let selectedNode = null;
    let dragMoved = false;

    const nodes = GRAPH.nodes.map((node, index) => ({{
      ...node,
      x: Math.cos(index * 0.7) * (120 + (index % 12) * 10),
      y: Math.sin(index * 0.7) * (120 + (index % 12) * 10),
      vx: 0,
      vy: 0,
      fx: null,
      fy: null,
    }}));
    const nodeById = new Map(nodes.map(node => [node.id, node]));
    const edges = GRAPH.edges.map(edge => ({{
      ...edge,
      source: nodeById.get(edge.source),
      target: nodeById.get(edge.target),
    }}));
    const adjacency = new Map();
    for (const edge of edges) {{
      if (!adjacency.has(edge.source.id)) adjacency.set(edge.source.id, new Set());
      if (!adjacency.has(edge.target.id)) adjacency.set(edge.target.id, new Set());
      adjacency.get(edge.source.id).add(edge.target.id);
      adjacency.get(edge.target.id).add(edge.source.id);
    }}

    const legendItems = GRAPH.legend || [];
    legend.innerHTML = legendItems.map(item =>
      `<div class="legend-item"><span class="swatch" style="background:${{item.color}}"></span><span>${{item.label}}</span></div>`
    ).join('');

    summary.innerHTML = (GRAPH.summaryLines || []).map(line => `<div>${{line}}</div>`).join('');

    function resize() {{
      const rect = canvas.parentElement.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(width * ratio);
      canvas.height = Math.floor(height * ratio);
      canvas.style.width = width + 'px';
      canvas.style.height = height + 'px';
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      draw();
    }}

    function fitView() {{
      if (!nodes.length) return;
      const xs = nodes.map(n => n.x);
      const ys = nodes.map(n => n.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const graphW = Math.max(1, maxX - minX);
      const graphH = Math.max(1, maxY - minY);
      scale = Math.min(width / (graphW + 180), height / (graphH + 180));
      offsetX = width / 2 - ((minX + maxX) / 2) * scale;
      offsetY = height / 2 - ((minY + maxY) / 2) * scale;
      draw();
    }}

    function worldToScreen(x, y) {{
      return {{ x: x * scale + offsetX, y: y * scale + offsetY }};
    }}

    function screenToWorld(x, y) {{
      return {{ x: (x - offsetX) / scale, y: (y - offsetY) / scale }};
    }}

    function getNodeRadius(node) {{
      return node.kind === 'job' ? 8 : node.kind === 'resource' ? 3 : 5;
    }}

    function getNodeColor(node) {{
      return node.color || '#94a3b8';
    }}

    function draw() {{
      ctx.clearRect(0, 0, width, height);

      const focusNode = selectedNode || hoveredNode;
      const neighborSet = focusNode ? adjacency.get(focusNode.id) || new Set() : new Set();

      for (const edge of edges) {{
        const a = worldToScreen(edge.source.x, edge.source.y);
        const b = worldToScreen(edge.target.x, edge.target.y);
        const active = focusNode && (
          edge.source.id === focusNode.id ||
          edge.target.id === focusNode.id ||
          (neighborSet.has(edge.source.id) && neighborSet.has(edge.target.id))
        );
        ctx.strokeStyle = active ? (edge.color || 'rgba(201,143,128,0.16)') : (edge.colorDim || 'rgba(188,181,177,0.018)');
        ctx.lineWidth = active ? 0.8 : 0.25;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }}

      for (const node of nodes) {{
        const p = worldToScreen(node.x, node.y);
        const r = getNodeRadius(node);
        const active = !focusNode || node.id === focusNode.id || neighborSet.has(node.id);
        ctx.globalAlpha = active ? 1 : 0.22;
        ctx.fillStyle = getNodeColor(node);
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.lineWidth = selectedNode && selectedNode.id === node.id ? 3 : 1.2;
        ctx.strokeStyle = selectedNode && selectedNode.id === node.id ? '#fffaf7' : 'rgba(140, 116, 108, 0.22)';
        ctx.stroke();
        if (showLabels) {{
          ctx.globalAlpha = active ? 1 : 0.18;
          ctx.fillStyle = '#755b55';
          ctx.font = '12px "Palatino Linotype", "STKaiti", serif';
          ctx.fillText(node.label, p.x + r + 6, p.y + 4);
        }}
      }}
      ctx.globalAlpha = 1;
    }}

    function stepPhysics() {{
      if (!physicsRunning) return;
      const repulsion = 10;
      const spring = 0.0000018;
      const damping = 0.992;
      const centering = 0.00008;

      for (let i = 0; i < nodes.length; i++) {{
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {{
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist2 = dx * dx + dy * dy + 0.01;
          const force = repulsion / dist2;
          const dist = Math.sqrt(dist2);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          if (a.fx === null) {{ a.vx += fx; a.vy += fy; }}
          if (b.fx === null) {{ b.vx -= fx; b.vy -= fy; }}
        }}
      }}

      for (const edge of edges) {{
        const a = edge.source;
        const b = edge.target;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
        const target = edge.length || 110;
        const force = (dist - target) * spring;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        if (a.fx === null) {{ a.vx += fx; a.vy += fy; }}
        if (b.fx === null) {{ b.vx -= fx; b.vy -= fy; }}
      }}

      let totalSpeed = 0;
      for (const node of nodes) {{
        if (node.fx !== null) {{
          node.x = node.fx;
          node.y = node.fy;
          node.vx = 0;
          node.vy = 0;
          continue;
        }}
        node.vx += (-node.x) * centering;
        node.vy += (-node.y) * centering;
        node.vx *= damping;
        node.vy *= damping;
        if (Math.abs(node.vx) < 0.0005) node.vx = 0;
        if (Math.abs(node.vy) < 0.0005) node.vy = 0;
        node.x += node.vx;
        node.y += node.vy;
        totalSpeed += Math.abs(node.vx) + Math.abs(node.vy);
      }}
    }}

    function animationFrame() {{
      stepPhysics();
      draw();
      requestAnimationFrame(animationFrame);
    }}

    function pickNode(screenX, screenY) {{
      const world = screenToWorld(screenX, screenY);
      for (let i = nodes.length - 1; i >= 0; i--) {{
        const node = nodes[i];
        const r = getNodeRadius(node) / scale + 3;
        const dx = node.x - world.x;
        const dy = node.y - world.y;
        if (dx * dx + dy * dy <= r * r) return node;
      }}
      return null;
    }}

    function renderDetails(node) {{
      if (!node) {{
        details.innerHTML = '点击节点查看详情';
        return;
      }}
      const metaRows = Object.entries(node.meta || {{}})
        .map(([k, v]) => `<div class="detail-row"><strong>${{k}}</strong>: ${{typeof v === 'object' ? JSON.stringify(v) : String(v)}}</div>`)
        .join('');
      details.innerHTML = `
        <div class="pill">${{node.kind}}</div>
        <div class="pill">${{node.label}}</div>
        <pre>${{JSON.stringify(node.payload || {{}}, null, 2)}}</pre>
        ${{metaRows}}
      `;
    }}

    canvas.addEventListener('mousedown', (event) => {{
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const node = pickNode(x, y);
      lastX = x;
      lastY = y;
      dragMoved = false;
      if (node) {{
        draggingNode = node;
        selectedNode = node;
        node.fx = screenToWorld(x, y).x;
        node.fy = screenToWorld(x, y).y;
        renderDetails(node);
      }} else {{
        panning = true;
      }}
      canvas.classList.add('dragging');
    }});

    canvas.addEventListener('mousemove', (event) => {{
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const node = pickNode(x, y);
      hoveredNode = node;
      if (draggingNode) {{
        const world = screenToWorld(x, y);
        draggingNode.fx = world.x;
        draggingNode.fy = world.y;
        if (Math.abs(x - lastX) > 2 || Math.abs(y - lastY) > 2) dragMoved = true;
      }} else if (panning) {{
        if (Math.abs(x - lastX) > 2 || Math.abs(y - lastY) > 2) dragMoved = true;
        offsetX += x - lastX;
        offsetY += y - lastY;
        lastX = x;
        lastY = y;
      }}
      draw();
    }});

    function stopDrag(event = null) {{
      if (panning && !dragMoved && event) {{
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        const node = pickNode(x, y);
        if (!node) {{
          selectedNode = null;
          renderDetails(null);
        }}
      }}
      if (draggingNode) {{
        draggingNode.fx = null;
        draggingNode.fy = null;
      }}
      draggingNode = null;
      panning = false;
      dragMoved = false;
      canvas.classList.remove('dragging');
    }}

    canvas.addEventListener('mouseup', (event) => stopDrag(event));
    canvas.addEventListener('mouseleave', () => {{
      hoveredNode = null;
      stopDrag();
    }});

    canvas.addEventListener('wheel', (event) => {{
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mouseX = event.clientX - rect.left;
      const mouseY = event.clientY - rect.top;
      const before = screenToWorld(mouseX, mouseY);
      const factor = event.deltaY < 0 ? 1.08 : 0.92;
      scale = Math.max(0.15, Math.min(4.5, scale * factor));
      const after = worldToScreen(before.x, before.y);
      offsetX += mouseX - after.x;
      offsetY += mouseY - after.y;
      draw();
    }}, {{ passive: false }});

    fitBtn.addEventListener('click', fitView);
    toggleLabelsBtn.addEventListener('click', () => {{
      showLabels = !showLabels;
      toggleLabelsBtn.textContent = showLabels ? '隐藏标签' : '显示标签';
      draw();
    }});

    window.addEventListener('resize', () => {{
      resize();
      fitView();
    }});

    resize();
    fitView();
    renderDetails(null);
    requestAnimationFrame(animationFrame);
  </script>
</body>
</html>
"""


def build_role_graph(role_id: str, prereq_depth: int, resource_limit: int, top_n: int = 15) -> dict[str, Any]:
    roles = load_roles()
    skill_graph = load_skill_graph()
    resources = load_resources()
    role = roles[role_id]
    top_skills = role_top_skills(role, top_n=top_n)

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    role_key = _node_key("job", role_id)
    nodes[role_key] = {
        "id": role_key,
        "label": role["role_name"],
        "kind": "job",
        "color": COLORS["job"],
        "payload": role,
        "meta": {"role_id": role_id, "coarse_role": role.get("coarse_role", "")},
    }

    def add_prereqs(skill_id: str, depth: int) -> None:
        if depth <= 0 or skill_id not in skill_graph:
            return
        for prereq_id in skill_graph[skill_id].get("prerequisites", []):
            if prereq_id not in skill_graph:
                continue
            prereq_key = _node_key("skill", prereq_id)
            prereq = skill_graph[prereq_id]
            nodes.setdefault(
                prereq_key,
                {
                    "id": prereq_key,
                    "label": prereq["skill_name"],
                    "kind": "skill",
                    "color": COLORS["skill"],
                    "payload": prereq,
                    "meta": {
                        "skill_id": prereq_id,
                        "level": prereq.get("level"),
                        "difficulty": prereq.get("difficulty"),
                        "hours_estimate": prereq.get("hours_estimate"),
                    },
                },
            )
            edges.append(
                {
                    "source": prereq_key,
                    "target": _node_key("skill", skill_id),
                    "label": "prereq",
                    "color": "rgba(148,163,184,0.85)",
                    "colorDim": "rgba(71,85,105,0.35)",
                    "length": 110,
                }
            )
            add_prereqs(prereq_id, depth - 1)

    for row in top_skills:
        skill_id = row["skill_id"]
        skill = skill_graph[skill_id]
        skill_key = _node_key("skill", skill_id)
        nodes.setdefault(
            skill_key,
            {
                "id": skill_key,
                "label": skill["skill_name"],
                "kind": "skill",
                "color": COLORS["skill"],
                "payload": skill,
                "meta": {
                    "skill_id": skill_id,
                    "importance_score": row["importance_score"],
                    "rank": row["rank"],
                    "level": skill.get("level"),
                    "difficulty": skill.get("difficulty"),
                    "hours_estimate": skill.get("hours_estimate"),
                },
            },
        )
        edges.append(
            {
                "source": role_key,
                "target": skill_key,
                "label": f"{row['rank']}:{row['importance_score']:.3f}",
                "color": "rgba(37,99,235,0.85)",
                "colorDim": "rgba(71,85,105,0.35)",
                "length": 150,
            }
        )
        add_prereqs(skill_id, prereq_depth)
        for resource in resources.get(skill_id, [])[:resource_limit]:
            resource_key = _node_key("resource", resource.resource_id)
            nodes.setdefault(
                resource_key,
                {
                    "id": resource_key,
                    "label": resource.title,
                    "kind": "resource",
                    "color": COLORS["resource"],
                    "payload": resource.model_dump(),
                    "meta": {
                        "resource_id": resource.resource_id,
                        "provider": resource.provider,
                        "level": resource.level,
                    },
                },
            )
            edges.append(
                {
                    "source": skill_key,
                    "target": resource_key,
                    "label": "resource",
                    "color": "rgba(245,158,11,0.85)",
                    "colorDim": "rgba(71,85,105,0.25)",
                    "length": 120,
                }
            )

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "summaryLines": [
            f"岗位: {role['role_name']}",
            f"Top{top_n} 技能已入图",
            f"先修展开深度: {prereq_depth}",
            f"资源展示: 每技能 {resource_limit} 个",
        ],
        "legend": [
            {"label": "岗位节点", "color": COLORS["job"]},
            {"label": "技能节点", "color": COLORS["skill"]},
            {"label": "资源节点", "color": COLORS["resource"]},
        ],
    }


def build_path_graph(role_id: str, resume_text: str, semantic_score: float) -> dict[str, Any]:
    roles = load_roles()
    skill_graph = load_skill_graph()
    profile = ExtractorService.extract(resume_text, None, "graph_viz_sample")
    analysis = GraphPathPlannerV2.analyze_role(profile, role_id, semantic_score=semantic_score)
    role = roles[role_id]

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    role_key = _node_key("job", role_id)
    nodes[role_key] = {
        "id": role_key,
        "label": role["role_name"],
        "kind": "job",
        "color": COLORS["job"],
        "payload": role,
        "meta": {
            "role_score": analysis.role_score,
            "semantic_score": analysis.semantic_score,
            "path_score": analysis.path.score,
        },
    }

    overlap_names = set(analysis.skill_gap.overlap_skills)
    missing_names = set(analysis.skill_gap.missing_skills)

    previous_key: str | None = None
    for step in analysis.path.steps:
        skill_id = next((sid for sid, info in skill_graph.items() if info["skill_name"] == step.skill), step.skill)
        skill_payload = skill_graph.get(skill_id, {"skill_name": step.skill})
        skill_key = _node_key("skill", skill_id)
        if step.skill in overlap_names:
            color = COLORS["overlap"]
        elif step.skill in missing_names:
            color = COLORS["missing"]
        else:
            color = COLORS["path"]
        nodes.setdefault(
            skill_key,
            {
                "id": skill_key,
                "label": step.skill,
                "kind": "skill",
                "color": color,
                "payload": skill_payload,
                "meta": {
                    "reason": step.reason,
                    "resources": [resource.title for resource in step.resources],
                },
            },
        )
        if previous_key is None:
            edges.append(
                {
                    "source": role_key,
                    "target": skill_key,
                    "label": "target path",
                    "color": "rgba(37,99,235,0.85)",
                    "colorDim": "rgba(71,85,105,0.35)",
                    "length": 150,
                }
            )
        else:
            edges.append(
                {
                    "source": previous_key,
                    "target": skill_key,
                    "label": f"step {len(edges)}",
                    "color": "rgba(168,85,247,0.85)",
                    "colorDim": "rgba(71,85,105,0.35)",
                    "length": 120,
                }
            )
        previous_key = skill_key

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "summaryLines": [
            f"岗位: {role['role_name']}",
            f"语义分: {analysis.semantic_score:.4f}",
            f"岗位分: {analysis.role_score:.4f}",
            f"路径分: {analysis.path.score:.4f}",
            f"总步数: {analysis.path.total_steps}",
            f"总学时: {analysis.path.total_estimated_hours}",
            f"用户技能: {', '.join(profile.skills)}",
        ],
        "legend": [
            {"label": "岗位节点", "color": COLORS["job"]},
            {"label": "路径技能节点", "color": COLORS["missing"]},
            {"label": "路径连接", "color": COLORS["path"]},
        ],
    }


def build_full_graph(include_resources: bool = False, resource_limit: int = 1, top_n: int = 15) -> dict[str, Any]:
    roles = load_roles()
    skill_graph = load_skill_graph()
    resources = load_resources()

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    for role_id, role in roles.items():
        role_key = _node_key("job", role_id)
        top_skills = role_top_skills(role, top_n=top_n)
        nodes[role_key] = {
            "id": role_key,
            "label": role["role_name"],
            "kind": "job",
            "color": COLORS["job"],
            "payload": role,
            "meta": {
                "role_id": role_id,
                "coarse_role": role.get("coarse_role", ""),
                "top_skill_count": len(top_skills),
            },
        }
        for row in top_skills:
            skill_id = row["skill_id"]
            if skill_id not in skill_graph:
                continue
            skill = skill_graph[skill_id]
            skill_key = _node_key("skill", skill_id)
            nodes.setdefault(
                skill_key,
                {
                    "id": skill_key,
                    "label": skill["skill_name"],
                    "kind": "skill",
                    "color": COLORS["skill"],
                    "payload": skill,
                    "meta": {
                        "skill_id": skill_id,
                        "level": skill.get("level"),
                        "difficulty": skill.get("difficulty"),
                        "hours_estimate": skill.get("hours_estimate"),
                    },
                },
            )
            edges.append(
                {
                    "source": role_key,
                    "target": skill_key,
                    "label": f"{row['rank']}:{row['importance_score']:.3f}",
                    "color": "rgba(37,99,235,0.72)",
                    "colorDim": "rgba(51,65,85,0.22)",
                    "length": 150,
                }
            )

    for skill_id, skill in skill_graph.items():
        skill_key = _node_key("skill", skill_id)
        nodes.setdefault(
            skill_key,
            {
                "id": skill_key,
                "label": skill["skill_name"],
                "kind": "skill",
                "color": COLORS["skill"],
                "payload": skill,
                "meta": {
                    "skill_id": skill_id,
                    "level": skill.get("level"),
                    "difficulty": skill.get("difficulty"),
                    "hours_estimate": skill.get("hours_estimate"),
                },
            },
        )
        for prereq_id in skill.get("prerequisites", []):
            if prereq_id not in skill_graph:
                continue
            prereq = skill_graph[prereq_id]
            prereq_key = _node_key("skill", prereq_id)
            nodes.setdefault(
                prereq_key,
                {
                    "id": prereq_key,
                    "label": prereq["skill_name"],
                    "kind": "skill",
                    "color": COLORS["skill"],
                    "payload": prereq,
                    "meta": {
                        "skill_id": prereq_id,
                        "level": prereq.get("level"),
                        "difficulty": prereq.get("difficulty"),
                        "hours_estimate": prereq.get("hours_estimate"),
                    },
                },
            )
            edges.append(
                {
                    "source": prereq_key,
                    "target": skill_key,
                    "label": "prereq",
                    "color": "rgba(148,163,184,0.7)",
                    "colorDim": "rgba(51,65,85,0.18)",
                    "length": 105,
                }
            )
        if include_resources:
            for resource in resources.get(skill_id, [])[:resource_limit]:
                resource_key = _node_key("resource", resource.resource_id)
                nodes.setdefault(
                    resource_key,
                    {
                        "id": resource_key,
                        "label": resource.title,
                        "kind": "resource",
                        "color": COLORS["resource"],
                        "payload": resource.model_dump(),
                        "meta": {
                            "resource_id": resource.resource_id,
                            "provider": resource.provider,
                            "level": resource.level,
                        },
                    },
                )
                edges.append(
                    {
                        "source": skill_key,
                        "target": resource_key,
                        "label": "resource",
                        "color": "rgba(245,158,11,0.72)",
                        "colorDim": "rgba(51,65,85,0.16)",
                        "length": 95,
                    }
                )

    job_count = sum(1 for node in nodes.values() if node["kind"] == "job")
    skill_count = sum(1 for node in nodes.values() if node["kind"] == "skill")
    resource_count = sum(1 for node in nodes.values() if node["kind"] == "resource")
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "summaryLines": [
            f"整图模式: 全职业 + 全技能{' + 资源' if include_resources else ''}",
            f"每个岗位仅显示 Top{top_n} 技能",
            f"岗位节点: {job_count}",
            f"技能节点: {skill_count}",
            f"资源节点: {resource_count}",
            f"边数: {len(edges)}",
        ],
        "legend": [
            {"label": "岗位节点", "color": COLORS["job"]},
            {"label": "技能节点", "color": COLORS["skill"]},
            {"label": "资源节点", "color": COLORS["resource"]},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export interactive HTML graph for role or path.")
    parser.add_argument("--role-id", default="role_011")
    parser.add_argument("--mode", choices=["role", "path", "full"], default="role")
    parser.add_argument("--prereq-depth", type=int, default=1)
    parser.add_argument("--resource-limit", type=int, default=1)
    parser.add_argument("--include-resources", action="store_true")
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--semantic-score", type=float, default=0.0)
    parser.add_argument("--resume-text", default="")
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if args.mode == "path":
        if not args.resume_text.strip():
            raise SystemExit("--mode path requires --resume-text")
        data = build_path_graph(args.role_id, args.resume_text.strip(), args.semantic_score)
        title = f"Interactive Path Graph - {args.role_id}"
        out_path = REPORT_DIR / f"{args.role_id}_path_graph_v2.html"
    elif args.mode == "full":
        data = build_full_graph(include_resources=args.include_resources, resource_limit=args.resource_limit, top_n=args.top_n)
        title = "Interactive Full Career Graph"
        suffix = "_with_resources" if args.include_resources else ""
        out_path = REPORT_DIR / f"full_career_graph_v2{suffix}.html"
    else:
        data = build_role_graph(args.role_id, args.prereq_depth, args.resource_limit, top_n=args.top_n)
        title = f"Interactive Role Graph - {args.role_id}"
        out_path = REPORT_DIR / f"{args.role_id}_role_graph_v2.html"

    out_path.write_text(_build_html(title, data), encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(out_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
