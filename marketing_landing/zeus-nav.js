// Zeus landing navigation: hamburger drawer (phone + tablet), header dropdowns (desktop) and the
// pinned bar that slides in on scroll. Works on any page that loads it: every
// `button[aria-label="Open menu"]` or `[data-zeus-menu-open]` opens the drawer.
(function () {
  "use strict";

  var REPO = "https://github.com/charanbalaji2005/Zeus-Agents";
  var SOCIAL = { Discord: "https://discord.com/users/1382355376539697272", GitHub: REPO, X: "https://x.com/charan7719" };
  var SIGN_IN = { label: "Sign in", action: "auth" };

  var PAGES = [
    { label: "Home", href: "/" },
    { label: "Install", href: "/#install" },
    { label: "Features", href: "/#features" },
    { label: "Downloads", href: "/#downloads" },
    { label: "Docs", href: "/docs" },
    { label: "Web CLI", href: "/cli" },
    { label: "Community", href: "/community.html" },
    { label: "FAQ", href: "/#faqs" },
    SIGN_IN,
  ];

  // Header dropdowns, keyed by the buttons' data-research-target.
  var DROPDOWNS = {
    Hermes: [PAGES[1], PAGES[2], PAGES[3], PAGES[4], PAGES[5], PAGES[7]],
    Community: [
      { label: "Community hub", href: "/community.html" },
      { label: "GitHub", href: REPO },
      { label: "Report an issue", href: REPO + "/issues/new" },
      { label: "Discord", href: SOCIAL.Discord },
      { label: "X / Twitter", href: SOCIAL.X },
    ],
    Nous: [{ label: "Built on Hermes Agent (Nous Research) ↗", href: "https://github.com/NousResearch/hermes-agent" }],
    Auth: [SIGN_IN],
    Portal: [SIGN_IN],
  };

  function isExternal(href) { return /^https?:\/\//.test(href) && href.indexOf(location.origin) !== 0; }

  function samePage(href) {
    var url = new URL(href, location.href);
    return url.pathname === location.pathname && !url.hash;
  }

  function signIn() {
    if (typeof window.openAuthModal === "function") window.openAuthModal();
    else location.href = "/#portal";
  }

  function makeItem(item, onDone) {
    var el;
    if (item.action === "auth") {
      el = document.createElement("button");
      el.type = "button";
      el.addEventListener("click", function () { onDone(); signIn(); });
    } else {
      el = document.createElement("a");
      el.href = item.href;
      if (isExternal(item.href)) { el.target = "_blank"; el.rel = "noopener"; }
      if (samePage(item.href)) el.setAttribute("aria-current", "page");
      el.addEventListener("click", onDone);
    }
    el.textContent = item.label;
    return el;
  }

  // ── Drawer ────────────────────────────────────────────────────────────────
  var drawer, backdrop, lastOpener;

  function buildDrawer() {
    backdrop = document.createElement("div");
    backdrop.className = "zeus-drawer-backdrop";
    backdrop.addEventListener("click", closeDrawer);

    drawer = document.createElement("nav");
    drawer.id = "zeus-drawer";
    drawer.className = "zeus-drawer";
    drawer.setAttribute("aria-label", "Site menu");

    var head = document.createElement("div");
    head.className = "zeus-drawer-head";
    var brand = document.createElement("a");
    brand.className = "zeus-drawer-brand";
    brand.href = "/";
    brand.innerHTML = "Zeus<br>Agents";
    var close = document.createElement("button");
    close.type = "button";
    close.className = "zeus-drawer-close";
    close.setAttribute("aria-label", "Close menu");
    close.innerHTML = "&times;";
    close.addEventListener("click", closeDrawer);
    head.appendChild(brand);
    head.appendChild(close);

    var list = document.createElement("ul");
    list.className = "zeus-drawer-links";
    PAGES.forEach(function (item) {
      var li = document.createElement("li");
      li.appendChild(makeItem(item, closeDrawer));
      list.appendChild(li);
    });

    var cta = makeItem({ label: "Install Zeus CLI", href: "/#install" }, closeDrawer);
    cta.className = "zeus-drawer-cta";

    var social = document.createElement("div");
    social.className = "zeus-drawer-social";
    Object.keys(SOCIAL).forEach(function (name) {
      social.appendChild(makeItem({ label: name, href: SOCIAL[name] }, closeDrawer));
    });

    drawer.appendChild(head);
    drawer.appendChild(list);
    drawer.appendChild(cta);
    drawer.appendChild(social);
    drawer.setAttribute("inert", "");
    document.body.appendChild(backdrop);
    document.body.appendChild(drawer);
  }

  function openers() {
    return document.querySelectorAll('button[aria-label="Open menu"], [data-zeus-menu-open]');
  }

  function setExpanded(value) {
    openers().forEach(function (b) { b.setAttribute("aria-expanded", value ? "true" : "false"); });
  }

  function openDrawer(opener) {
    closeDropdown();
    lastOpener = opener || null;
    drawer.removeAttribute("inert");
    document.documentElement.classList.add("zeus-nav-open");
    setExpanded(true);
    var first = drawer.querySelector(".zeus-drawer-links a, .zeus-drawer-links button");
    if (first) first.focus({ preventScroll: true });
  }

  function closeDrawer() {
    if (!document.documentElement.classList.contains("zeus-nav-open")) return;
    document.documentElement.classList.remove("zeus-nav-open");
    drawer.setAttribute("inert", "");
    setExpanded(false);
    if (lastOpener && document.contains(lastOpener)) lastOpener.focus({ preventScroll: true });
  }

  function trapFocus(e) {
    if (e.key !== "Tab" || !document.documentElement.classList.contains("zeus-nav-open")) return;
    var items = drawer.querySelectorAll("a, button");
    var first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  // ── Dropdowns ─────────────────────────────────────────────────────────────
  var dropdown, dropdownOwner;

  function closeDropdown() {
    if (!dropdown || dropdown.hidden) return;
    dropdown.hidden = true;
    if (dropdownOwner) dropdownOwner.setAttribute("aria-expanded", "false");
    dropdownOwner = null;
  }

  function openDropdown(button) {
    var items = DROPDOWNS[button.getAttribute("data-research-target")];
    if (!items) return;
    if (dropdownOwner === button) { closeDropdown(); return; }
    closeDropdown();
    if (!dropdown) {
      dropdown = document.createElement("ul");
      dropdown.id = "zeus-dropdown";
      dropdown.className = "zeus-dropdown";
      document.body.appendChild(dropdown);
    }
    dropdown.textContent = "";
    items.forEach(function (item) {
      var li = document.createElement("li");
      li.appendChild(makeItem(item, closeDropdown));
      dropdown.appendChild(li);
    });
    dropdown.hidden = false;
    var r = button.getBoundingClientRect();
    var left = Math.min(r.left, window.innerWidth - dropdown.offsetWidth - 12);
    dropdown.style.left = Math.max(12, left) + "px";
    dropdown.style.top = r.bottom + 10 + "px";
    dropdownOwner = button;
    button.setAttribute("aria-controls", "zeus-dropdown");
    button.setAttribute("aria-expanded", "true");
  }

  // ── Pinned bar ────────────────────────────────────────────────────────────
  function syncPinned() {
    var bar = document.querySelector(".marketing-paper-nav");
    if (!bar) return;
    var show = window.scrollY > Math.max(480, window.innerHeight * 0.7);
    bar.classList.toggle("zeus-pinned-shown", show);
    if (show) bar.removeAttribute("inert"); else bar.setAttribute("inert", "");
  }

  function init() {
    buildDrawer();
    openers().forEach(function (button) {
      button.setAttribute("aria-controls", "zeus-drawer");
      button.setAttribute("aria-expanded", "false");
      button.addEventListener("click", function (e) {
        e.preventDefault();
        if (document.documentElement.classList.contains("zeus-nav-open")) closeDrawer(); else openDrawer(button);
      });
    });
    document.querySelectorAll("button.nw-subnav-trigger[data-research-target]").forEach(function (button) {
      button.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); openDropdown(button); });
    });
    document.addEventListener("click", function (e) {
      if (dropdown && !dropdown.hidden && !dropdown.contains(e.target)) closeDropdown();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { closeDropdown(); closeDrawer(); }
      trapFocus(e);
    });
    window.addEventListener("scroll", function () { closeDropdown(); syncPinned(); }, { passive: true });
    window.addEventListener("resize", function () { closeDropdown(); if (window.innerWidth >= 1200) closeDrawer(); });
    syncPinned();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
