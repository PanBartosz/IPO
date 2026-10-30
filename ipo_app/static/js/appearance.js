(() => {
  "use strict";
  const form = document.getElementById("appearance-form");
  const preview = document.querySelector("[data-appearance-preview]");
  if (!form || !preview) return;
  const palettes = JSON.parse(document.getElementById("appearance-palettes").textContent);
  const colorPattern = /^#[0-9a-f]{6}$/i;
  const fonts = {
    raleway: '"Raleway", system-ui, -apple-system, "Segoe UI", sans-serif',
    condensed: '"Roboto Condensed", "Arial Narrow", system-ui, -apple-system, "Segoe UI", sans-serif',
    system: 'system-ui, -apple-system, "Segoe UI", sans-serif',
    serif: 'Georgia, "Times New Roman", serif',
  };
  const corners = {current: [12, 16, 22], square: [3, 5, 8], rounded: [18, 24, 32]};
  const value = name => form.elements.namedItem(name)?.value || "";
  const checked = name => Boolean(form.elements.namedItem(name)?.checked);
  const rgb = color => [1, 3, 5].map(start => parseInt(color.slice(start, start + 2), 16)).join(", ");
  const set = (name, property) => {
    const color = value(name);
    if (colorPattern.test(color)) preview.style.setProperty(property, color);
  };

  function updatePreview(dirty = true) {
    for (const [name, property] of Object.entries({primary: "--brand-purple", accent: "--brand-magenta", highlight: "--brand-orange", text: "--text", button_text: "--button-text", header_background: "--header-bg", header_text: "--header-text", footer_background: "--footer-bg", page_background: "--page-bg"})) set(name, property);
    for (const name of ["primary", "accent", "highlight", "text", "surface", "header_text", "footer_text"]) {
      if (colorPattern.test(value(name))) preview.style.setProperty(`--${name.replaceAll("_", "-")}-rgb`, rgb(value(name)));
    }
    if (colorPattern.test(value("surface"))) preview.style.setProperty("--surface", `rgba(${rgb(value("surface"))}, 0.94)`);
    if (colorPattern.test(value("text"))) {
      preview.style.setProperty("--text-muted", `rgba(${rgb(value("text"))}, 0.72)`);
      preview.style.setProperty("--border", `rgba(${rgb(value("text"))}, 0.14)`);
    }
    preview.style.setProperty("--brand-gradient", checked("gradient_enabled") ? "linear-gradient(270deg, var(--brand-purple) 0%, var(--brand-magenta) 45%, var(--brand-orange) 100%)" : value("primary"));
    preview.dataset.decorations = checked("decorations_enabled") ? "on" : "off";
    preview.style.setProperty("--font-body", fonts[value("body_font")]);
    preview.style.setProperty("--font-heading", fonts[value("heading_font")]);
    preview.style.setProperty("--header-logo-width", `${Math.max(32, Math.min(140, Number(value("header_logo_width")) || 56))}px`);
    preview.style.fontSize = ({small: "13px", standard: "14px", large: "16px"})[value("font_size")];
    for (const [index, name] of ["sm", "md", "lg"].entries()) preview.style.setProperty(`--radius-${name}`, `${(corners[value("corners")] || corners.current)[index]}px`);
    document.querySelectorAll("[data-preview-text]").forEach(node => { node.textContent = value(node.dataset.previewText); });
    preview.querySelector("[data-preview-footer]").hidden = !checked("footer_enabled");
    preview.querySelector("[data-preview-partners]").hidden = !checked("partners_enabled");
    if (dirty) {
      const status = document.getElementById("appearance-preview-status");
      status.textContent = "Unsaved preview";
      status.dataset.dirty = "true";
    }
  }

  form.addEventListener("input", () => updatePreview());
  form.addEventListener("change", () => updatePreview());
  document.querySelectorAll("[data-color]").forEach(input => input.addEventListener("input", () => {
    document.querySelector(`[data-hex="${input.dataset.color}"]`).value = input.value.toUpperCase();
  }));
  document.querySelectorAll("[data-hex]").forEach(input => input.addEventListener("input", () => {
    const valid = colorPattern.test(input.value);
    input.setAttribute("aria-invalid", String(!valid));
    input.setCustomValidity(valid ? "" : "Use a six-digit hex color, for example #822D80.");
    if (valid) {
      form.elements.namedItem(input.dataset.hex).value = input.value;
      updatePreview();
    }
  }));
  form.addEventListener("submit", event => {
    const invalid = [...document.querySelectorAll("[data-hex]")].find(input => !colorPattern.test(input.value));
    if (invalid) { event.preventDefault(); invalid.reportValidity(); invalid.focus(); }
  });
  document.querySelectorAll("[data-palette]").forEach(button => button.addEventListener("click", () => {
    const colors = {...palettes.warsaw.colors, ...palettes[button.dataset.palette].colors};
    for (const [name, color] of Object.entries(colors)) {
      form.elements.namedItem(name).value = color;
      const hex = document.querySelector(`[data-hex="${name}"]`);
      hex.value = color;
      hex.setCustomValidity("");
      hex.setAttribute("aria-invalid", "false");
    }
    document.querySelectorAll("[data-palette]").forEach(item => item.setAttribute("aria-pressed", String(item === button)));
    updatePreview();
  }));
  document.querySelectorAll("[data-image-slot]").forEach(input => input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (!file) return;
    const container = document.querySelector(`[data-image-preview="${input.dataset.imageSlot}"]`);
    const image = document.createElement("img");
    const objectUrl = URL.createObjectURL(file);
    image.alt = "Selected image preview";
    image.addEventListener("load", () => URL.revokeObjectURL(objectUrl), {once: true});
    image.addEventListener("error", () => URL.revokeObjectURL(objectUrl), {once: true});
    image.src = objectUrl;
    container.replaceChildren(image);
  }));
  updatePreview(false);
})();
