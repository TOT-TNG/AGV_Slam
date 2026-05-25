/**
 * sidebar_menu.js — Client-side submenu toggle.
 * Handles expand/collapse of sidebar submenus instantly without Dash round-trips.
 * Navigation (display_page) always renders the correct initial state from Python.
 */
(function () {
  // Event delegation on document so it works even after Dash re-renders the sidebar
  document.addEventListener('click', function (e) {
    var mapHeader  = e.target.closest('#menu-map');
    var taskHeader = e.target.closest('#menu-task');

    if (!mapHeader && !taskHeader) return;

    var mapMenu  = document.getElementById('submenu-map');
    var taskMenu = document.getElementById('submenu-task');

    if (mapHeader) {
      // Toggle map, always close task
      if (mapMenu)  mapMenu.classList.toggle('open');
      if (taskMenu) taskMenu.classList.remove('open');
    } else if (taskHeader) {
      // Toggle task, always close map
      if (taskMenu) taskMenu.classList.toggle('open');
      if (mapMenu)  mapMenu.classList.remove('open');
    }
  }, false);
})();
