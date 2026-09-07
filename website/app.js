/* SztuCode 官网交互 */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── 顶部导航滚动态 ─────────────────── */
  var topbar = document.getElementById("topbar");
  function onScroll() {
    if (!topbar) return;
    topbar.classList.toggle("scrolled", window.scrollY > 12);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ── 移动端菜单 ─────────────────────── */
  var burger = document.getElementById("navBurger");
  var mobileMenu = document.getElementById("mobileMenu");
  if (burger && mobileMenu) {
    burger.addEventListener("click", function () {
      var open = burger.getAttribute("aria-expanded") === "true";
      burger.setAttribute("aria-expanded", String(!open));
      mobileMenu.classList.toggle("open", !open);
      burger.setAttribute("aria-label", open ? "打开菜单" : "关闭菜单");
    });
    mobileMenu.addEventListener("click", function (e) {
      if (e.target && e.target.tagName === "A") {
        burger.setAttribute("aria-expanded", "false");
        mobileMenu.classList.remove("open");
      }
    });
  }

  /* ── 滚动入场 ───────────────────────── */
  var revealEls = document.querySelectorAll(".reveal, .reveal-late");
  if ("IntersectionObserver" in window && !reduceMotion) {
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach(function (el) { io.observe(el); });
    // 首屏元素立即入场
    window.addEventListener("load", function () {
      document.querySelectorAll(".hero .reveal, .hero .reveal-late").forEach(function (el) {
        el.classList.add("in");
      });
    });
  } else {
    revealEls.forEach(function (el) { el.classList.add("in"); });
  }

  /* ── Hero 输入框打字机循环 ───────────── */
  var typeEl = document.getElementById("typeText");
  if (typeEl && !reduceMotion) {
    var phrases = [
      "把调研报告整理成 10 页汇报 PPT",
      "修复 src 下的 typecheck 报错",
      "把课程成绩表转成图表并核对数据",
    ];
    var p = 0, c = 0, deleting = false;
    var tick = function () {
      var phrase = phrases[p];
      if (!deleting) {
        c += 1;
        typeEl.textContent = phrase.slice(0, c);
        if (c === phrase.length) {
          deleting = true;
          setTimeout(tick, 2100);
          return;
        }
        setTimeout(tick, 62 + Math.random() * 46);
      } else {
        c -= 1;
        typeEl.textContent = phrase.slice(0, c);
        if (c === 0) {
          deleting = false;
          p = (p + 1) % phrases.length;
          setTimeout(tick, 420);
          return;
        }
        setTimeout(tick, 26);
      }
    };
    setTimeout(tick, 1300);
  } else if (typeEl) {
    typeEl.textContent = "把调研报告整理成 10 页汇报 PPT";
  }

  /* ── 下载按钮防止空跳 ───────────────── */
  document.querySelectorAll('a[href="#download"]').forEach(function (a) {
    a.addEventListener("click", function (e) {
      var target = document.getElementById("download");
      if (!target) { e.preventDefault(); }
    });
  });
})();
