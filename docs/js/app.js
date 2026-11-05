// JS-rendered test content for Visualping. Self-hosted, no dependencies.
// Uses textContent everywhere (never innerHTML), so data.json can't inject markup.
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  function li(text) {
    var el = document.createElement("li");
    el.textContent = text;
    return el;
  }

  function start(data) {
    $("js-message").textContent = String(data.message);

    // Content that only appears after a delay.
    setTimeout(function () {
      $("delayed").textContent = String(data.delayed);
      $("delayed").hidden = false;
    }, 5000);

    // Carousel: auto-advances every 4 seconds, plus Prev/Next buttons.
    var slides = data.slides.map(function (text, i) {
      var el = document.createElement("div");
      el.className = "slide";
      el.id = "slide-" + (i + 1);
      el.textContent = String(text);
      el.hidden = i !== 0;
      $("slides").appendChild(el);
      return el;
    });
    var current = 0;
    function show(n) {
      slides[current].hidden = true;
      current = (n + slides.length) % slides.length;
      slides[current].hidden = false;
    }
    $("prev").addEventListener("click", function () { show(current - 1); });
    $("next").addEventListener("click", function () { show(current + 1); });
    setInterval(function () { show(current + 1); }, 4000);

    // Load more: 4 items at first, 4 more per click.
    var shown = 0;
    function loadMore() {
      data.items.slice(shown, shown + 4).forEach(function (t) { $("item-list").appendChild(li(String(t))); });
      shown = Math.min(shown + 4, data.items.length);
      $("load-more").hidden = shown >= data.items.length;
      filter();
    }
    function filter() {
      var q = $("search").value.toLowerCase();
      Array.prototype.forEach.call($("item-list").children, function (el) {
        el.hidden = q !== "" && el.textContent.toLowerCase().indexOf(q) === -1;
      });
    }
    $("load-more").addEventListener("click", loadMore);
    $("search").addEventListener("input", filter);
    loadMore();
  }

  // Fake login: nothing is stored or sent. It only reveals hidden content.
  $("login-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var name = $("username").value.trim();
    $("password").value = "";
    if (!name) { return; }
    $("welcome").textContent = "Welcome, " + name + " (fake login).";
    $("members").hidden = false;
    $("login-form").hidden = true;
  });

  // Pop-up after 2 seconds, cookie banner right away. Both reappear on every load.
  setTimeout(function () { $("popup").hidden = false; }, 2000);
  $("popup-close").addEventListener("click", function () { $("popup").hidden = true; });
  $("cookie-banner").hidden = false;
  $("cookie-accept").addEventListener("click", function () { $("cookie-banner").hidden = true; });
  $("cookie-reject").addEventListener("click", function () { $("cookie-banner").hidden = true; });

  fetch("data.json", { cache: "no-store" })
    .then(function (r) { return r.json(); })
    .then(start)
    .catch(function () { $("js-message").textContent = "Could not load data.json"; });
})();
