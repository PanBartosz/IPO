(() => {
  const THUMB_SELECTOR = "figure img";

  const previousOverflow = { html: "", body: "" };

  function lockScroll() {
    previousOverflow.html = document.documentElement.style.overflow;
    previousOverflow.body = document.body.style.overflow;
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
  }

  function unlockScroll() {
    document.documentElement.style.overflow = previousOverflow.html;
    document.body.style.overflow = previousOverflow.body;
  }

  function ensureLightbox() {
    let root = document.getElementById("manual-lightbox");
    if (root) return root;

    root = document.createElement("div");
    root.id = "manual-lightbox";
    root.className = "manual-lightbox";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-label", "Screenshot preview");

    root.innerHTML = `
      <div class="manual-lightbox__dialog" role="document">
        <div class="manual-lightbox__header">
          <div class="manual-lightbox__title" id="manual-lightbox-title"></div>
          <button type="button" class="manual-lightbox__close" id="manual-lightbox-close" aria-label="Close preview">
            Close
          </button>
        </div>
        <div class="manual-lightbox__body">
          <img class="manual-lightbox__img" id="manual-lightbox-img" alt="" />
          <div class="manual-lightbox__caption" id="manual-lightbox-caption"></div>
        </div>
      </div>
    `;

    document.body.appendChild(root);

    root.addEventListener("click", (event) => {
      if (event.target === root) closeLightbox();
    });

    root.querySelector("#manual-lightbox-close")?.addEventListener("click", closeLightbox);
    root.querySelector("#manual-lightbox-img")?.addEventListener("click", closeLightbox);

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && root.classList.contains("is-open")) {
        closeLightbox();
      }
    });

    return root;
  }

  function openLightbox(img) {
    const root = ensureLightbox();
    const modalImg = root.querySelector("#manual-lightbox-img");
    const title = root.querySelector("#manual-lightbox-title");
    const caption = root.querySelector("#manual-lightbox-caption");

    const figure = img.closest("figure");
    const figcaption = figure?.querySelector("figcaption");
    const captionText = (figcaption?.textContent || img.alt || "").trim();

    if (modalImg) {
      modalImg.src = img.getAttribute("src") || "";
      modalImg.alt = captionText || "Screenshot";
    }
    if (title) title.textContent = captionText ? `Preview — ${captionText}` : "Preview";
    if (caption) caption.textContent = captionText;

    root.classList.add("is-open");
    lockScroll();
  }

  function closeLightbox() {
    const root = document.getElementById("manual-lightbox");
    if (!root) return;
    root.classList.remove("is-open");
    unlockScroll();
  }

  function init() {
    document.querySelectorAll(THUMB_SELECTOR).forEach((img) => {
      img.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        openLightbox(img);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

