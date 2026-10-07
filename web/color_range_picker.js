import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_TYPE = "ARCHVIZColorRangeMask";

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name);
}

function setWidgetValue(node, name, value) {
  const widget = getWidget(node, name);
  if (!widget) return;
  widget.value = value;
  widget.callback?.(value, app.canvas, node, [0, 0], null);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function sourceImage(node) {
  if (node.__archvizColorRangeExecutedPreview?.complete) {
    return node.__archvizColorRangeExecutedPreview;
  }
  if (!node.imgs?.length) return null;
  const index = Number.isInteger(node.imageIndex) ? node.imageIndex : 0;
  return node.imgs[clamp(index, 0, node.imgs.length - 1)] ?? node.imgs[0];
}

function captureExecutedPreview(node, message, refresh) {
  const images = message?.images;
  if (!Array.isArray(images) || !images.length) return;

  const info = images[0];
  if (!info?.filename) return;

  const params = new URLSearchParams();
  params.set("filename", info.filename);
  if (info.subfolder) params.set("subfolder", info.subfolder);
  params.set("type", info.type || "temp");

  const img = new Image();
  img.onload = () => {
    node.__archvizColorRangeExecutedPreview = img;
    refresh?.();
  };
  img.src = api.apiURL("/view?" + params.toString());
}

function sampleRgb(img, imageX, imageY) {
  const width = img.naturalWidth || img.width;
  const height = img.naturalHeight || img.height;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, 0, 0, width, height);

  const x = clamp(Math.floor(imageX), 0, width - 1);
  const y = clamp(Math.floor(imageY), 0, height - 1);
  const pixel = ctx.getImageData(x, y, 1, 1).data;
  return [pixel[0], pixel[1], pixel[2]];
}

function rgbToHex(rgb) {
  return "#" + rgb.map((value) => clamp(Math.round(value), 0, 255)
    .toString(16).padStart(2, "0")).join("").toUpperCase();
}

function createPicker(node) {
  const root = document.createElement("div");
  root.style.cssText = [
    "display:flex",
    "flex-direction:column",
    "gap:6px",
    "width:100%",
    "height:100%",
    "font:12px sans-serif",
    "color:#ddd",
    "background:#111",
    "padding:8px",
    "box-sizing:border-box",
  ].join(";");

  const toolbar = document.createElement("div");
  toolbar.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;";

  const pick = document.createElement("button");
  pick.textContent = "🎯 PICK COLOR";
  pick.style.cssText =
    "cursor:pointer;background:#d7b51d;color:#111;border:0;border-radius:4px;padding:6px 9px;font-weight:700;";

  const swatch = document.createElement("span");
  swatch.style.cssText =
    "width:24px;height:24px;border:1px solid #777;border-radius:3px;display:inline-block;";

  const meta = document.createElement("code");
  meta.style.cssText = "color:#ccc";

  toolbar.append(pick, swatch, meta);

  const status = document.createElement("div");
  status.textContent = "Queue once to load the current beauty image, then pick a representative color.";
  status.style.cssText = "color:#999;font-size:11px;";

  const canvas = document.createElement("canvas");
  canvas.style.cssText =
    "width:100%;height:auto;max-height:420px;object-fit:contain;background:#080808;border:1px solid #333;cursor:crosshair;";

  root.append(toolbar, status, canvas);

  const state = { picking: false };

  function selectedRgb() {
    return ["red", "green", "blue"].map(
      (name) => Number(getWidget(node, name)?.value ?? 0),
    );
  }

  function render() {
    const rgb = selectedRgb();
    swatch.style.background = `rgb(${rgb.join(",")})`;
    meta.textContent = `${rgb.join(" / ")}  ${rgbToHex(rgb)}`;

    const img = sourceImage(node);
    const ctx = canvas.getContext("2d");

    if (!img) {
      canvas.width = 640;
      canvas.height = 150;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#888";
      ctx.font = "14px sans-serif";
      ctx.fillText("Waiting for executed input preview...", 14, 28);
      return;
    }

    if (!img.complete || !(img.naturalWidth || img.width)) {
      img.addEventListener("load", render, { once: true });
      return;
    }

    const width = img.naturalWidth || img.width;
    const height = img.naturalHeight || img.height;
    const scale = Math.min(1, 720 / width, 380 / height);
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));

    ctx.imageSmoothingEnabled = true;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    const sx = Number(getWidget(node, "seed_x")?.value ?? 0);
    const sy = Number(getWidget(node, "seed_y")?.value ?? 0);
    if (sx >= 0 && sy >= 0 && sx < width && sy < height) {
      const px = sx / width * canvas.width;
      const py = sy / height * canvas.height;
      ctx.strokeStyle = "#ffd400";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(px, py, 6, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  pick.addEventListener("click", () => {
    state.picking = !state.picking;
    pick.textContent = state.picking ? "🎯 CLICK BEAUTY PREVIEW" : "🎯 PICK COLOR";
    status.textContent = state.picking
      ? "Click a representative point inside the target material."
      : "Picker ready.";
  });

  canvas.addEventListener("click", (event) => {
    if (!state.picking) return;
    const img = sourceImage(node);
    if (!img) return;

    const rect = canvas.getBoundingClientRect();
    const nx = clamp((event.clientX - rect.left) / rect.width, 0, 0.999999);
    const ny = clamp((event.clientY - rect.top) / rect.height, 0, 0.999999);
    const width = img.naturalWidth || img.width;
    const height = img.naturalHeight || img.height;
    const imageX = nx * width;
    const imageY = ny * height;
    const rgb = sampleRgb(img, imageX, imageY);

    setWidgetValue(node, "red", rgb[0]);
    setWidgetValue(node, "green", rgb[1]);
    setWidgetValue(node, "blue", rgb[2]);
    setWidgetValue(node, "seed_x", Math.floor(imageX));
    setWidgetValue(node, "seed_y", Math.floor(imageY));

    state.picking = false;
    pick.textContent = "🎯 PICK COLOR";
    status.textContent =
      `Picked x=${Math.floor(imageX)}, y=${Math.floor(imageY)}. Queue to calculate Hybrid/Connected mask.`;

    app.graph?.setDirtyCanvas(true, true);
    render();
  });

  node.__archvizRenderColorRange = render;
  requestAnimationFrame(render);
  for (const delay of [50, 150, 400, 900]) {
    setTimeout(render, delay);
  }
  return root;
}

app.registerExtension({
  name: "ARCHVIZ.ColorRangeMask",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE) return;

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalOnNodeCreated?.apply(this, arguments);

      this.addDOMWidget(
        "archviz_color_range_picker",
        "ARCHVIZ_COLOR_RANGE_PICKER",
        createPicker(this),
        {
          serialize: false,
          getMinHeight: () => 280,
          getMaxHeight: () => 520,
        },
      );

      this.setSize([
        Math.max(this.size?.[0] ?? 320, 440),
        Math.max(this.size?.[1] ?? 420, 700),
      ]);
    };

    const originalOnExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      originalOnExecuted?.apply(this, arguments);
      captureExecutedPreview(this, message, this.__archvizRenderColorRange);
      setTimeout(() => this.__archvizRenderColorRange?.(), 0);
    };

    const originalOnConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      originalOnConfigure?.apply(this, arguments);
      setTimeout(() => this.__archvizRenderColorRange?.(), 0);
    };
  },
});
