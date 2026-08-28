/* ==========================================================================
   NOCTRA wireframe kit — shared app shell.
   Injects the dashboard chrome (sidebar + topbar) exactly as implemented in
   dashboard/src/layouts/DashboardLayout/index.tsx and
   dashboard/src/components/Navbar/index.tsx.

   Usage: <body class="wf-doc" data-active="inbox"> with elements
   <aside data-sidebar></aside> and <header data-topbar></header>.
   The active nav item is highlighted by data-active.
   ========================================================================= */

(function () {
  "use strict";

  // Nav groups mirror DashboardLayout exactly (spec §8 — the analyst loop).
  var NAV = [
    {
      group: "Main",
      items: [
        { id: "inbox", name: "Home", path: "analyst-inbox.html" },
        { id: "feed", name: "Cases", path: "cases-feed.html" },
        { id: "actions", name: "Actions", path: "actions-log.html" },
        { id: "reports", name: "Reports", path: "reports.html" },
      ],
    },
    {
      group: "Investigate",
      items: [
        { id: "alerts", name: "Alerts", path: "alerts.html" },
        { id: "entities", name: "Entities & Graph", path: "entities.html" },
        { id: "analytics", name: "Analytics", path: "analytics.html" },
        { id: "dashboard", name: "SOC Cockpit", path: "soc-cockpit.html" },
        { id: "incidents", name: "Manual Incidents", path: "incidents.html" },
        { id: "logs", name: "Log Uploads", path: "logs.html" },
      ],
    },
    {
      group: "Automate",
      items: [
        { id: "soar", name: "SOAR", path: "soar.html" },
        { id: "rules", name: "Rules", path: "admin-config.html#rules" },
      ],
    },
    {
      group: "System",
      items: [
        { id: "audit", name: "Audit", path: "admin-config.html#system-logs" },
        { id: "reputation", name: "Reputation", path: "admin-config.html#reputation" },
        { id: "engine", name: "Engine", path: "admin-config.html#engine" },
        { id: "admin", name: "Admin Overview", path: "admin.html" },
        { id: "users", name: "Users", path: "admin-users.html" },
        { id: "tenants", name: "Tenants", path: "admin-users.html#tenants" },
        { id: "roles", name: "Roles", path: "admin-users.html#roles" },
      ],
    },
  ];

  function iconEl() {
    var i = document.createElement("i");
    i.className = "ico";
    return i;
  }

  function renderSidebar(host, active) {
    var brand = document.createElement("div");
    brand.className = "wf-brand";
    brand.innerHTML =
      '<span class="wf-brand-name">' +
      '<svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">' +
      '<path d="M20.4 14.2A8.6 8.6 0 0 1 9.8 3.6a.7.7 0 0 0-.9-.86 10 10 0 1 0 12.36 12.36.7.7 0 0 0-.86-.9z" fill="#7163d2"/>' +
      "</svg>" +
      "<span>NOCTRA</span></span>" +
      '<i class="ico" style="width:18px;height:18px;border-radius:999px"></i>';

    var nav = document.createElement("nav");
    nav.setAttribute("aria-label", "Primary");

    NAV.forEach(function (group, gi) {
      if (gi > 0) {
        var sep = document.createElement("div");
        sep.className = "wf-nav-sep";
        nav.appendChild(sep);
      }
      var label = document.createElement("p");
      label.className = "wf-nav-group";
      label.textContent = group.group;
      nav.appendChild(label);

      group.items.forEach(function (item) {
        var a = document.createElement("a");
        a.className = "wf-nav-item" + (item.id === active ? " active" : "");
        a.href = item.path;
        a.appendChild(iconEl());
        var span = document.createElement("span");
        span.textContent = item.name;
        a.appendChild(span);
        if (item.id === active) a.setAttribute("aria-current", "page");
        nav.appendChild(a);
      });
    });

    var user = document.createElement("div");
    user.className = "wf-user";
    user.innerHTML =
      '<span class="wf-avatar">D</span>' +
      '<span class="who"><p>demo</p><span>analyst</span></span>' +
      '<i class="ico" style="width:15px;height:15px;border-radius:4px"></i>';

    host.appendChild(brand);
    host.appendChild(nav);
    host.appendChild(user);
  }

  function renderTopbar(host) {
    host.innerHTML =
      '<i class="ico" style="width:18px;height:18px;border-radius:5px;display:inline-block;border:1.4px solid #c4c4bc"></i>' + // mobile menu
      '<svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">' +
      '<path d="M20.4 14.2A8.6 8.6 0 0 1 9.8 3.6a.7.7 0 0 0-.9-.86 10 10 0 1 0 12.36 12.36.7.7 0 0 0-.86-.9z" fill="#7163d2"/></svg>' +
      '<span class="wf-tagline">Your autonomous security analyst.</span>' +
      '<span class="wf-search">Search IP, threat, hash… <span class="kbd">⌘K</span></span>' +
      '<span class="wf-top-actions">' +
      '<i class="ico" style="width:15px;height:15px;border-radius:999px;display:inline-block;border:1.4px solid #c4c4bc"></i>' + // theme toggle
      '<span class="wf-reviewpill">Review decisions <span class="count">2</span></span>' +
      '<span class="wf-iconbtn"><i class="ico" style="width:14px;height:14px;border-radius:4px;display:inline-block;border:1.4px solid currentColor;opacity:.6"></i><span class="dotbadge">3</span></span>' +
      '<span class="wf-avatar">D</span>' +
      "</span>";
  }

  document.addEventListener("DOMContentLoaded", function () {
    var body = document.body;
    var active = body.getAttribute("data-active");
    var sidebar = body.querySelector("[data-sidebar]");
    var topbar = body.querySelector("[data-topbar]");
    if (sidebar) renderSidebar(sidebar, active);
    if (topbar) renderTopbar(topbar);
  });
})();
