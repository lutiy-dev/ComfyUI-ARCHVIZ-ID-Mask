import { app } from "../../scripts/app.js";

const PALETTE_NODE = "ARCHVIZIDPalettePicker";
const SINGLE_NODE = "ARCHVIZMaskFromPalette";
const GROUP_NODE = "ARCHVIZIDGroupMask";

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name);
}

function setWidget(node, name, value) {
  const widget = getWidget(node, name);
  if (!widget) return;
  widget.value = value;
  widget.callback?.(value, app.canvas, node, [0, 0], null);
}

function hideWidget(node, name) {
  const widget = getWidget(node, name);
  if (!widget) return;
  widget.computeSize = () => [0, -4];
  widget.type = "hidden";
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function rgbToHex(rgb) {
  return "#" + rgb.map((v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, "0")).join("").toUpperCase();
}

function parsePalette(node) {
  try {
    const raw = getWidget(node, "palette_json")?.value || '{"version":1,"colors":[]}';
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed.colors)) throw new Error();
    return parsed;
  } catch {
    return { version: 1, colors: [] };
  }
}

function refreshPaletteConsumers() {
  const nodes = app.graph?._nodes || [];
  for (const item of nodes) {
    item.__archvizPaletteSelectorRefresh?.();
    item.__archvizGroupSelectorRefresh?.();
  }
}

function savePalette(node, palette) {
  setWidget(node, "palette_json", JSON.stringify(palette));
  app.graph?.setDirtyCanvas(true, true);
  queueMicrotask(refreshPaletteConsumers);
}

function sourceImage(node) {
  if (!node.imgs?.length) return null;
  const index = Number.isInteger(node.imageIndex) ? node.imageIndex : 0;
  return node.imgs[clamp(index, 0, node.imgs.length - 1)] ?? node.imgs[0];
}

function sampleRgb(img, imageX, imageY, radius) {
  const width = img.naturalWidth || img.width;
  const height = img.naturalHeight || img.height;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, 0, 0, width, height);

  const cx = Math.floor(imageX), cy = Math.floor(imageY);
  const x0 = clamp(cx - radius, 0, width - 1), y0 = clamp(cy - radius, 0, height - 1);
  const x1 = clamp(cx + radius, 0, width - 1), y1 = clamp(cy + radius, 0, height - 1);
  const data = ctx.getImageData(x0, y0, x1 - x0 + 1, y1 - y0 + 1).data;
  let r = 0, g = 0, b = 0, count = 0;
  for (let i = 0; i < data.length; i += 4) {
    r += data[i]; g += data[i + 1]; b += data[i + 2]; count++;
  }
  return [Math.round(r / count), Math.round(g / count), Math.round(b / count)];
}

function makeId() {
  return globalThis.crypto?.randomUUID?.() || ("color-" + Date.now() + "-" + Math.random().toString(16).slice(2));
}

function createPaletteUi(node) {
  hideWidget(node, "palette_json");
  const root = document.createElement("div");
  root.style.cssText = "display:flex;flex-direction:column;gap:8px;background:#111;color:#ddd;padding:8px;box-sizing:border-box;font:12px sans-serif;height:100%;";

  const add = document.createElement("button");
  add.textContent = "+ ADD COLOR";
  add.style.cssText = "background:#d7b51d;color:#111;border:0;border-radius:4px;padding:7px;font-weight:700;cursor:pointer;";

  const status = document.createElement("div");
  status.style.cssText = "color:#999;font-size:11px";
  status.textContent = "Queue once, then add a color and click the ID preview.";

  const canvas = document.createElement("canvas");
  canvas.style.cssText = "width:100%;height:auto;max-height:330px;background:#080808;border:1px solid #333;cursor:crosshair;";

  const list = document.createElement("div");
  list.style.cssText = "display:flex;flex-direction:column;gap:6px;max-height:240px;overflow:auto;";

  root.append(add, status, canvas, list);
  let activeId = null;

  function renderList() {
    list.replaceChildren();
    const palette = parsePalette(node);
    palette.colors.forEach((color, index) => {
      const row = document.createElement("div");
      row.style.cssText = "display:grid;grid-template-columns:24px 1fr auto;gap:6px;align-items:center;border:1px solid #333;padding:6px;border-radius:4px;";

      const swatch = document.createElement("span");
      swatch.style.cssText = "width:20px;height:20px;border:1px solid #777;background:" + (color.hex || rgbToHex(color.rgb)) + ";display:inline-block;";

      const middle = document.createElement("div");
      const name = document.createElement("input");
      name.value = color.name || ("Color " + (index + 1));
      name.style.cssText = "width:100%;background:#1b1b1b;color:#eee;border:1px solid #444;padding:4px;box-sizing:border-box;";
      const meta = document.createElement("code");
      meta.textContent = color.rgb.join(" / ") + "  " + (color.hex || rgbToHex(color.rgb));
      meta.style.cssText = "display:block;color:#aaa;font-size:10px;margin-top:3px;";

      name.addEventListener("change", () => {
        const p = parsePalette(node);
        const item = p.colors.find((x) => x.id === color.id);
        if (item) item.name = name.value.trim() || ("Color " + (index + 1));
        savePalette(node, p);
      });

      middle.append(name, meta);

      const del = document.createElement("button");
      del.textContent = "×";
      del.style.cssText = "background:#2b2b2b;color:#ddd;border:1px solid #555;border-radius:3px;cursor:pointer;";
      del.addEventListener("click", () => {
        const p = parsePalette(node);
        p.colors = p.colors.filter((x) => x.id !== color.id);
        savePalette(node, p);
        if (activeId === color.id) activeId = null;
        renderList();
      });

      row.addEventListener("click", (event) => {
        if (event.target === name || event.target === del) return;
        activeId = color.id;
        status.textContent = "Selected slot: " + color.name + ". Click preview to resample.";
      });

      row.append(swatch, middle, del);
      list.append(row);
    });
  }

  function renderImage() {
    const img = sourceImage(node);
    const ctx = canvas.getContext("2d");
    if (!img || !img.complete) {
      canvas.width = 620; canvas.height = 150;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#888"; ctx.font = "14px sans-serif";
      ctx.fillText("No executed ID preview yet.", 12, 26);
      return;
    }
    const w = img.naturalWidth || img.width, h = img.naturalHeight || img.height;
    const scale = Math.min(1, 700 / w, 320 / h);
    canvas.width = Math.max(1, Math.round(w * scale));
    canvas.height = Math.max(1, Math.round(h * scale));
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  }

  add.addEventListener("click", () => {
    const p = parsePalette(node);
    const id = makeId();
    p.colors.push({ id, name: "Color " + (p.colors.length + 1), rgb: [0, 0, 0], hex: "#000000" });
    activeId = id;
    savePalette(node, p);
    status.textContent = "New slot added. Click the required ID color.";
    renderList();
  });

  canvas.addEventListener("click", (event) => {
    if (!activeId) {
      status.textContent = "Add or select a palette slot first.";
      return;
    }
    const img = sourceImage(node);
    if (!img) return;
    const rect = canvas.getBoundingClientRect();
    const nx = clamp((event.clientX - rect.left) / rect.width, 0, 0.999999);
    const ny = clamp((event.clientY - rect.top) / rect.height, 0, 0.999999);
    const imageX = nx * (img.naturalWidth || img.width);
    const imageY = ny * (img.naturalHeight || img.height);
    const radius = Number(getWidget(node, "sample_radius")?.value || 0);
    const rgb = sampleRgb(img, imageX, imageY, radius);

    const p = parsePalette(node);
    const item = p.colors.find((x) => x.id === activeId);
    if (!item) return;
    item.rgb = rgb;
    item.hex = rgbToHex(rgb);
    savePalette(node, p);
    status.textContent = "Picked x=" + Math.floor(imageX) + ", y=" + Math.floor(imageY) + " → " + item.hex;
    renderList();
  });

  node.__archvizPaletteRefresh = () => { renderImage(); renderList(); };
  requestAnimationFrame(node.__archvizPaletteRefresh);
  return root;
}

function nodeHasPaletteState(node) {
  return Boolean(getWidget(node, "palette_json"));
}

function resolvePaletteSource(node, visited = new Set()) {
  if (!node || visited.has(node.id)) return null;
  visited.add(node.id);

  if (nodeHasPaletteState(node)) return node;

  for (const input of node.inputs || []) {
    if (input.link == null) continue;
    const link = app.graph?.links?.[input.link];
    if (!link) continue;
    const upstream = app.graph?.getNodeById?.(link.origin_id);
    const found = resolvePaletteSource(upstream, visited);
    if (found) return found;
  }
  return null;
}

function upstreamPaletteNode(node) {
  const paletteInput = node.inputs?.find((x) => x.name === "palette");
  if (!paletteInput || paletteInput.link == null) return null;
  const link = app.graph?.links?.[paletteInput.link];
  if (!link) return null;
  return resolvePaletteSource(app.graph?.getNodeById?.(link.origin_id));
}

function paletteFromConnection(node) {
  const upstream = upstreamPaletteNode(node);
  return upstream ? parsePalette(upstream) : { version: 1, colors: [] };
}

function createSingleSelector(node) {
  hideWidget(node, "color_id");
  const root = document.createElement("div");
  root.style.cssText = "display:flex;gap:6px;align-items:center;background:#111;color:#ddd;padding:6px;font:12px sans-serif;";
  const select = document.createElement("select");
  select.style.cssText = "flex:1;background:#1c1c1c;color:#eee;border:1px solid #555;padding:5px;";
  const refresh = document.createElement("button");
  refresh.textContent = "↻";
  refresh.style.cssText = "background:#292929;color:#ddd;border:1px solid #555;padding:5px 8px;cursor:pointer;";
  root.append(select, refresh);

  function sync() {
    const palette = paletteFromConnection(node);
    const current = String(getWidget(node, "color_id")?.value || "");
    select.replaceChildren();
    for (const color of palette.colors) {
      select.add(new Option(color.name + " · " + (color.hex || rgbToHex(color.rgb)), color.id));
    }
    if (palette.colors.some((x) => x.id === current)) {
      select.value = current;
    } else if (palette.colors[0]) {
      select.value = palette.colors[0].id;
      setWidget(node, "color_id", palette.colors[0].id);
    } else {
      setWidget(node, "color_id", "");
    }
  }

  select.addEventListener("change", () => setWidget(node, "color_id", select.value));
  refresh.addEventListener("click", sync);
  node.__archvizPaletteSelectorRefresh = sync;
  requestAnimationFrame(sync);
  return root;
}

function createGroupSelector(node) {
  hideWidget(node, "color_ids_json");
  const root = document.createElement("div");
  root.style.cssText = "display:flex;flex-direction:column;gap:5px;background:#111;color:#ddd;padding:6px;font:12px sans-serif;";
  const refresh = document.createElement("button");
  refresh.textContent = "↻ REFRESH PALETTE";
  refresh.style.cssText = "background:#292929;color:#ddd;border:1px solid #555;padding:5px 8px;cursor:pointer;";
  const list = document.createElement("div");
  list.style.cssText = "display:flex;flex-direction:column;gap:4px;max-height:180px;overflow:auto;";
  root.append(refresh, list);

  function currentIds() {
    try {
      const value = JSON.parse(getWidget(node, "color_ids_json")?.value || "[]");
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  }

  function sync() {
    const palette = paletteFromConnection(node);
    const validIds = new Set(palette.colors.map((color) => color.id));
    const selected = new Set(currentIds().filter((id) => validIds.has(id)));
    const stored = currentIds();
    if (stored.length !== selected.size || stored.some((id) => !selected.has(id))) {
      setWidget(node, "color_ids_json", JSON.stringify([...selected]));
    }
    list.replaceChildren();
    for (const color of palette.colors) {
      const label = document.createElement("label");
      label.style.cssText = "display:flex;gap:6px;align-items:center;";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = selected.has(color.id);
      const swatch = document.createElement("span");
      swatch.style.cssText = "width:14px;height:14px;border:1px solid #777;background:" + (color.hex || rgbToHex(color.rgb)) + ";display:inline-block;";
      const text = document.createElement("span");
      text.textContent = color.name + " · " + (color.hex || rgbToHex(color.rgb));
      box.addEventListener("change", () => {
        const ids = new Set(currentIds());
        if (box.checked) ids.add(color.id); else ids.delete(color.id);
        setWidget(node, "color_ids_json", JSON.stringify([...ids]));
      });
      label.append(box, swatch, text);
      list.append(label);
    }
  }

  refresh.addEventListener("click", sync);
  node.__archvizGroupSelectorRefresh = sync;
  requestAnimationFrame(sync);
  return root;
}

function attachDom(nodeType, factory, minHeight) {
  const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    originalOnNodeCreated?.apply(this, arguments);
    this.addDOMWidget("archviz_palette_ui", "ARCHVIZ_PALETTE_UI", factory(this), {
      serialize: false,
      getMinHeight: () => minHeight,
      getMaxHeight: () => minHeight + 260,
    });
    this.setSize([Math.max(this.size?.[0] || 320, 420), Math.max(this.size?.[1] || 300, minHeight + 220)]);
  };

  const originalOnExecuted = nodeType.prototype.onExecuted;
  nodeType.prototype.onExecuted = function () {
    originalOnExecuted?.apply(this, arguments);
    setTimeout(() => {
      this.__archvizPaletteRefresh?.();
      this.__archvizPaletteSelectorRefresh?.();
      this.__archvizGroupSelectorRefresh?.();
    }, 0);
  };

  const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
  nodeType.prototype.onConnectionsChange = function () {
    originalOnConnectionsChange?.apply(this, arguments);
    setTimeout(() => {
      this.__archvizPaletteSelectorRefresh?.();
      this.__archvizGroupSelectorRefresh?.();
    }, 0);
  };
}

app.registerExtension({
  name: "ARCHVIZ.IDPaletteSystem",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === PALETTE_NODE) attachDom(nodeType, createPaletteUi, 420);
    if (nodeData.name === SINGLE_NODE) attachDom(nodeType, createSingleSelector, 80);
    if (nodeData.name === GROUP_NODE) attachDom(nodeType, createGroupSelector, 180);
  },
});
