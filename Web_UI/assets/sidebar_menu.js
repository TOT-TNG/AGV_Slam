/**
 * sidebar_menu.js — Client-side submenu toggle.
 * Handles expand/collapse of sidebar submenus instantly without Dash round-trips.
 */
(function () {
  document.addEventListener('click', function (e) {
    var mapHeader  = e.target.closest('#menu-map');
    var taskHeader = e.target.closest('#menu-task');
    var logHeader  = e.target.closest('#menu-log');

    if (!mapHeader && !taskHeader && !logHeader) return;

    var mapMenu  = document.getElementById('submenu-map');
    var taskMenu = document.getElementById('submenu-task');
    var logMenu  = document.getElementById('submenu-log');

    if (mapHeader) {
      if (mapMenu)  mapMenu.classList.toggle('open');
      if (taskMenu) taskMenu.classList.remove('open');
      if (logMenu)  logMenu.classList.remove('open');
    } else if (taskHeader) {
      if (taskMenu) taskMenu.classList.toggle('open');
      if (mapMenu)  mapMenu.classList.remove('open');
      if (logMenu)  logMenu.classList.remove('open');
    } else if (logHeader) {
      if (logMenu)  logMenu.classList.toggle('open');
      if (mapMenu)  mapMenu.classList.remove('open');
      if (taskMenu) taskMenu.classList.remove('open');
    }
  }, false);
})();
