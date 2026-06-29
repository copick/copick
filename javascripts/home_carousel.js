/* Home-page showcase carousel.
 *
 * Progressive enhancement of the static markup in index.md: turns the stacked
 * `.cp-carousel__slide` sections into a tabbed carousel. Each slide's title
 * becomes an always-visible, clickable tab; the matching slide is shown and the
 * deck advances on a slow autoplay timer (paused while the reader interacts).
 * Without JS (or under reduced-motion) all slides stay visible/readable.
 *
 * Hooks Zensical's instant-navigation observable (`document$`, also used by
 * mathjax.js) so it re-initializes after client-side page swaps.
 */

function initCarousel(carousel) {
  if (carousel.dataset.cpInit === "1") {
    return; // already enhanced (guards against double subscribe on same DOM)
  }
  const slides = Array.from(carousel.querySelectorAll(".cp-carousel__slide"));
  if (slides.length === 0) {
    return;
  }
  carousel.dataset.cpInit = "1";
  carousel.classList.add("cp-carousel--ready");

  let index = 0;
  let timer = null;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const interval = parseInt(carousel.dataset.autoplay || "7000", 10);

  // --- Build the tab bar from each slide's title ---
  const tabsWrap = document.createElement("div");
  tabsWrap.className = "cp-carousel__tabs";
  tabsWrap.setAttribute("role", "tablist");
  const tabs = slides.map(function (slide, k) {
    const titleEl = slide.querySelector(".cp-carousel__title");
    const label = titleEl ? titleEl.textContent.trim() : "Slide " + (k + 1);
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "cp-carousel__tab";
    tab.setAttribute("role", "tab");
    tab.textContent = label;
    tab.addEventListener("click", function () {
      show(k);
      restart();
    });
    tabsWrap.appendChild(tab);
    return tab;
  });
  carousel.insertBefore(tabsWrap, carousel.firstChild);

  function show(i) {
    index = (i + slides.length) % slides.length;
    slides.forEach(function (s, k) {
      s.classList.toggle("is-active", k === index);
    });
    tabs.forEach(function (t, k) {
      t.classList.toggle("is-active", k === index);
      t.setAttribute("aria-selected", k === index ? "true" : "false");
    });
  }
  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }
  function start() {
    if (reduceMotion || slides.length < 2) {
      return;
    }
    stop();
    timer = setInterval(function () {
      show(index + 1);
    }, interval);
  }
  function restart() {
    stop();
    start();
  }

  // Pause autoplay while the reader is interacting with the carousel.
  carousel.addEventListener("mouseenter", stop);
  carousel.addEventListener("mouseleave", start);
  carousel.addEventListener("focusin", stop);
  carousel.addEventListener("focusout", start);

  show(0);
  start();
}

function initCarousels() {
  document.querySelectorAll(".cp-carousel").forEach(initCarousel);
}

if (typeof window.document$ !== "undefined" && window.document$.subscribe) {
  window.document$.subscribe(function () {
    initCarousels();
  });
} else {
  document.addEventListener("DOMContentLoaded", initCarousels);
}
