/**
 * sidebar_menu.js — Client-side submenu toggle + single-active accordion.
 * Handles expand/collapse of sidebar submenus instantly without Dash round-trips.
 * Chỉ 1 nhóm menu được mở/highlight tại 1 thời điểm: mở nhóm nào thì mọi nhóm
 * khác tự đóng lại và mất highlight ngay (kể cả khi chưa điều hướng trang thật —
 * lúc điều hướng thật, Dash sẽ render lại sidebar từ pathname nên luôn khớp).
 */
(function () {
  var GROUPS = [
    { header: '#menu-map',      menu: '#submenu-map' },
    { header: '#menu-task',     menu: '#submenu-task' },
    { header: '#menu-log',      menu: '#submenu-log' },
    { header: '#menu-settings', menu: '#submenu-settings' },
  ];

  document.addEventListener('click', function (e) {
    var clicked = null;
    for (var i = 0; i < GROUPS.length; i++) {
      if (e.target.closest(GROUPS[i].header)) { clicked = GROUPS[i]; break; }
    }
    if (!clicked) return;

    var clickedMenuEl   = document.querySelector(clicked.menu);
    var clickedHeaderEl = document.querySelector(clicked.header);
    var willOpen = !!(clickedMenuEl && !clickedMenuEl.classList.contains('open'));

    // Đóng + bỏ highlight TẤT CẢ nhóm khác (không bao giờ 2 nhóm cùng mở/highlight)
    GROUPS.forEach(function (g) {
      if (g === clicked) return;
      var menuEl   = document.querySelector(g.menu);
      var headerEl = document.querySelector(g.header);
      if (menuEl) {
        menuEl.classList.remove('open');
        menuEl.querySelectorAll('.submenu-item.active').forEach(function (el) {
          el.classList.remove('active');
        });
      }
      if (headerEl) headerEl.classList.remove('active');
    });

    if (clickedMenuEl) clickedMenuEl.classList.toggle('open');
    if (clickedHeaderEl) clickedHeaderEl.classList.toggle('active', willOpen);
    if (!willOpen && clickedMenuEl) {
      clickedMenuEl.querySelectorAll('.submenu-item.active').forEach(function (el) {
        el.classList.remove('active');
      });
    }
  }, false);
})();
