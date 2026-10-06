import { app } from "../../scripts/app.js";

const NODE_TYPE = "ARCHVIZIDColorPickerMask";

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function setWidgetValue(node, name, value) {
  const widget = getWidget(node, name);
  if (!widget) return;
  widget.value = value;
  widget.callback?.(value, app.canvas, node, [0, 0], null);
}

function selectedRgb(node) {
  return ["red", "green", "blue"].map(
    (name) => Number(getWidget(node, name)?.value ?? 0),
  );
}

function sampleRadius(node) {
  return Number(getWidget(node, "sample_radius")?.value ?? 0);
}

function tolerance(node) {
  return Number(getWidget(node, "tolerance")?.value ?? 5);
}

function rgbToHex(rgb) {
  return `#${rgb
    .map((value) =>
      clamp(Math.round(value), 0, 255)
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")
    .toUpperCase()}`;
}

function sourceImage(node) {
  if (!node.imgs?.length) return null;
  const index = Number.isInteger(node.imageIndex) ? node.imageIndex : 0;
  return node.imgs[clamp(index, 0, node.imgs.length - 1)] ?? node.imgs[0];
}

function sampleOriginalRgb(img, imageX, imageY, radius) {
  const width = img.naturalWidth || img.width;
  const height = img.naturalHeight || img.height;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, 0, 0, width, height);

  const cx = Math.floor(imageX);
  const cy = Math.floor(imageY);
  const x0 = clamp(cx - radius, 0, width - 1);
  const y0 = clamp(cy - radius, 0, height - 1);
  const x1 = clamp(cx + radius, 0, width - 1);
  const y1 = clamp(cy + radius, 0, height - 1);
  const blockWidth = x1 - x0 + 1;
  const blockHeight = y1 - y0 + 1;
  const data = ctx.getImageData(x0, y0, blockWidth, blockHeight).data;

  let red = 0;
  let green = 0;
  let blue = 0;
  let count = 0;

  for (let i = 0; i < data.length; i += 4) {
    red += data[i];
    green += data[i + 1];
    blue += data[i + 2];
    count += 1;
  }

  return [
    Math.round(red / count),
    Math.round(green / count),
    Math.round(blue / count),
  ];
}

function buildLocalMask(img, rgb, maxTolerance, maxWidth = 640) {
  const sourceWidth = img.naturalWidth || img.width;
  const sourceHeight = img.naturalHeight || img.height;
  const scale = Math.min(1, maxWidth / sourceWidth);
  const width = Math.max(1, Math.round(sourceWidth * scale));
  const height = Math.max(1, Math.round(sourceHeight * scale));

  const sourceCanvas = document.createElement("canvas");
  sourceCanvas.width = width;
  sourceCanvas.height = height;
  const sourceCtx = sourceCanvas.getContext("2d", { willReadFrequently: true });
  sourceCtx.imageSmoothingEnabled = false;
  sourceCtx.drawImage(img, 0, 0, width, height);

  const source = sourceCtx.getImageData(0, 0, width, height);
  const output = sourceCtx.createImageData(width, height);
  const [sr, sg, sb] = rgb;

  for (let i = 0; i < source.data.length; i += 4) {
    const dr = source.data[i] - sr;
    const dg = source.data[i + 1] - sg;
    const db = source.data[i + 2] - sb;
    const hit = Math.sqrt(dr * dr + dg * dg + db * db) <= maxTolerance;
    const value = hit ? 255 : 0;
    output.data[i] = value;
    output.data[i + 1] = value;
    output.data[i + 2] = value;
    output.data[i + 3] = 255;
  }

  const result = document.createElement("canvas");
  result.width = width;
  result.height = height;
  result.getContext("2d").putImageData(output, 0, 0);
  return result;
}

function createPickerElement(node) {
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
  toolbar.style.cssText =
    "display:flex;gap:6px;align-items:center;flex-wrap:wrap;";

  const pickButton = document.createElement("button");
  pickButton.textContent = "🎯 PICK COLOR";
  pickButton.style.cssText =
    "cursor:pointer;background:#d7b51d;color:#111;border:0;border-radius:4px;padding:6px 9px;font-weight:700;";

  const idButton = document.createElement("button");
  idButton.textContent = "ID";
  const maskButton = document.createElement("button");
  maskButton.textContent = "MASK";

  for (const button of [idButton, maskButton]) {
    button.style.cssText =
      "cursor:pointer;background:#292929;color:#ddd;border:1px solid #555;border-radius:4px;padding:5px 8px;";
  }

  const swatch = document.createElement("span");
  swatch.style.cssText =
    "width:24px;height:24px;border:1px solid #777;border-radius:3px;display:inline-block;";

  const colorLabel = document.createElement("code");
  colorLabel.style.cssText = "color:#ccc";

  toolbar.append(pickButton, idButton, maskButton, swatch, colorLabel);

  const status = document.createElement("div");
  status.textContent =
    "Queue once to load the current ID pass, then pick a color.";
  status.style.cssText = "color:#999;font-size:11px;";

  const canvas = document.createElement("canvas");
  canvas.style.cssText =
    "width:100%;height:auto;max-height:420px;object-fit:contain;background:#080808;border:1px solid #333;cursor:crosshair;";

  root.append(toolbar, status, canvas);

  const state = {
    canvas,
    colorLabel,
    mode: "ID",
    pickButton,
    picking: false,
    status,
    swatch,
  };
  node.__archvizIdPicker = state;

  function updateColorMeta() {
    const rgb = selectedRgb(node);
    state.swatch.style.background = `rgb(${rgb.join(",")})`;
    state.colorLabel.textContent = `${rgb.join(" / ")}  ${rgbToHex(rgb)}`;
  }

  function render() {
    updateColorMeta();
    const img = sourceImage(node);
    const ctx = canvas.getContext("2d");

    if (!img || !img.complete) {
      canvas.width = 640;
      canvas.height = 160;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#888";
      ctx.font = "14px sans-serif";
      ctx.fillText("No executed input preview yet.", 14, 28);
      return;
    }

    const source =
      state.mode === "MASK"
        ? buildLocalMask(img, selectedRgb(node), tolerance(node))
        : img;

    const width = source.naturalWidth || source.width;
    const height = source.naturalHeight || source.height;
    const scale = Math.min(1, 720 / width, 380 / height);
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
  }

  pickButton.addEventListener("click", () => {
    state.picking = !state.picking;
    pickButton.textContent = state.picking
      ? "🎯 CLICK ID PREVIEW"
      : "🎯 PICK COLOR";
    status.textContent = state.picking
      ? "Click the exact ID region in the preview."
      : "Picker ready.";
  });

  idButton.addEventListener("click", () => {
    state.mode = "ID";
    render();
  });

  maskButton.addEventListener("click", () => {
    state.mode = "MASK";
    render();
  });

  canvas.addEventListener("click", (event) => {
    if (!state.picking) return;

    const img = sourceImage(node);
    if (!img) return;

    const rect = canvas.getBoundingClientRect();
    const nx = clamp((event.clientX - rect.left) / rect.width, 0, 0.999999);
    const ny = clamp((event.clientY - rect.top) / rect.height, 0, 0.999999);
    const imageX = nx * (img.naturalWidth || img.width);
    const imageY = ny * (img.naturalHeight || img.height);
    const rgb = sampleOriginalRgb(
      img,
      imageX,
      imageY,
      sampleRadius(node),
    );

    setWidgetValue(node, "red", rgb[0]);
    setWidgetValue(node, "green", rgb[1]);
    setWidgetValue(node, "blue", rgb[2]);

    state.picking = false;
    pickButton.textContent = "🎯 PICK COLOR";
    status.textContent =
      `Picked source pixel x=${Math.floor(imageX)}, y=${Math.floor(imageY)}. Queue to update workflow outputs.`;

    app.graph?.setDirtyCanvas(true, true);
    render();
  });

  node.__archvizRenderIdPicker = render;
  requestAnimationFrame(render);
  return root;
}

app.registerExtension({
  name: "ARCHVIZ.IDColorPickerMask",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE) return;

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalOnNodeCreated?.apply(this, arguments);

      this.addDOMWidget(
        "archviz_id_picker",
        "ARCHVIZ_ID_PICKER",
        createPickerElement(this),
        {
          serialize: false,
          getMinHeight: () => 300,
          getMaxHeight: () => 520,
        },
      );

      this.setSize([
        Math.max(this.size?.[0] ?? 320, 420),
        Math.max(this.size?.[1] ?? 420, 620),
      ]);
    };

    const originalOnExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function () {
      originalOnExecuted?.apply(this, arguments);
      setTimeout(() => this.__archvizRenderIdPicker?.(), 0);
    };

    const originalOnConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      originalOnConfigure?.apply(this, arguments);
      setTimeout(() => this.__archvizRenderIdPicker?.(), 0);
    };
  },
});
