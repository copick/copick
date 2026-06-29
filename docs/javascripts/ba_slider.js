/* Before/after comparison slider (Tools gallery cards).
 *
 * Progressive enhancement of the static markup emitted by make_cli_docs
 * (`_slider_card`): each `.ba-slider[data-ba]` holds two stacked images
 * (`.ba-slider__before` over `.ba-slider__after`). This adds a draggable wipe
 * handle that sets the `--pos` CSS variable (0-100%), which the CSS uses to clip
 * the top (before) image — drag to reveal more input vs. result. Without JS the
 * card falls back to the static 50/50 split from the inline `--pos:50%`.
 *
 * Hooks Zensical's instant-navigation observable (`document$`, also used by
 * home_carousel.js / mathjax.js) so it re-initializes after client-side swaps.
 */

function initSlider(slider) {
  if (slider.dataset.baInit === "1") {
    return; // already enhanced (guards against double subscribe on same DOM)
  }
  slider.dataset.baInit = "1";

  // --- Build the divider + handle and the corner labels ---
  const divider = document.createElement("span");
  divider.className = "ba-slider__divider";
  divider.setAttribute("aria-hidden", "true");
  const handle = document.createElement("span");
  handle.className = "ba-slider__handle";
  divider.appendChild(handle);

  const labelBefore = document.createElement("span");
  labelBefore.className = "ba-slider__label ba-slider__label--before";
  labelBefore.textContent = "Input";
  const labelAfter = document.createElement("span");
  labelAfter.className = "ba-slider__label ba-slider__label--after";
  labelAfter.textContent = "Output";

  slider.appendChild(labelBefore);
  slider.appendChild(labelAfter);
  slider.appendChild(divider);

  // --- Accessibility: behave as a horizontal slider ---
  slider.setAttribute("role", "slider");
  slider.setAttribute("aria-label", "Before / after comparison");
  slider.setAttribute("aria-valuemin", "0");
  slider.setAttribute("aria-valuemax", "100");
  slider.tabIndex = 0;

  let pos = 50;

  function setPos(value) {
    pos = Math.max(0, Math.min(100, value));
    slider.style.setProperty("--pos", pos + "%");
    slider.setAttribute("aria-valuenow", Math.round(pos));
  }

  function posFromEvent(event) {
    const rect = slider.getBoundingClientRect();
    if (rect.width === 0) {
      return pos;
    }
    return ((event.clientX - rect.left) / rect.width) * 100;
  }

  let dragging = false;

  slider.addEventListener("pointerdown", function (event) {
    dragging = true;
    slider.setPointerCapture(event.pointerId);
    setPos(posFromEvent(event));
    event.preventDefault();
  });
  slider.addEventListener("pointermove", function (event) {
    if (dragging) {
      setPos(posFromEvent(event));
    }
  });
  function endDrag(event) {
    if (dragging) {
      dragging = false;
      try {
        slider.releasePointerCapture(event.pointerId);
      } catch (e) {
        /* pointer already released */
      }
    }
  }
  slider.addEventListener("pointerup", endDrag);
  slider.addEventListener("pointercancel", endDrag);

  slider.addEventListener("keydown", function (event) {
    const step = event.shiftKey ? 10 : 4;
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
      setPos(pos - step);
    } else if (event.key === "ArrowRight" || event.key === "ArrowUp") {
      setPos(pos + step);
    } else if (event.key === "Home") {
      setPos(0);
    } else if (event.key === "End") {
      setPos(100);
    } else {
      return;
    }
    event.preventDefault();
  });

  // Initialize from the inline default (or fall back to 50).
  const initial = parseFloat((slider.style.getPropertyValue("--pos") || "50").replace("%", ""));
  setPos(isNaN(initial) ? 50 : initial);
}

function initSliders() {
  document.querySelectorAll(".ba-slider[data-ba]").forEach(initSlider);
}

if (typeof window.document$ !== "undefined" && window.document$.subscribe) {
  window.document$.subscribe(function () {
    initSliders();
  });
} else {
  document.addEventListener("DOMContentLoaded", initSliders);
}
