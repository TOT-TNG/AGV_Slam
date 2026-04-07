# i18n.py
# Global translation helper for the Dash app.

DEFAULT_LANG = "vi"
SUPPORTED_LANGS = ("en", "vi")

TRANSLATIONS = {
    "en": {
        # Top/side common
        "app.title": "TOT ACS",
        "topbar.title": "AGV Control System (ACS)",
        "lang.label": "Language",
        "lang.en": "English",
        "lang.vi": "Vietnamese",
        "account.logout": "Logout",

        "menu.home": "Home",
        "menu.map": "Map",
        "menu.map.create": "Create Map",
        "menu.map.configure": "Map Configure",
        "menu.map.agvmap": "AGV Map",
        "menu.task": "Task Manager",
        "menu.task.create": "Create Task",
        "menu.task.list": "Task List",
        "menu.agv": "AGV Manager",
        "menu.log": "Log",
        "menu.stat": "Statistic",
        "menu.help": "Help",

        # Home
        "home.title": "System Overview",
        "home.card.agv_online": "AGV Online",
        "home.card.agv_online.desc": "Currently active AGVs",
        "home.card.tasks_today": "Tasks Today",
        "home.card.tasks_today.desc": "Total tasks executed",
        "home.card.errors": "Errors",
        "home.card.errors.desc": "Reported system issues",
        "home.chart.title": "Task Status Distribution",
        "home.legend.title": "Task Status",

        # Task list
        "task_list.title": "Task List",

        # Create map
        "create_map.toolbox": "Toolbox",
        "create_map.node": "Node",
        "create_map.properties": "Properties",
        "create_map.zoom": "Zoom",
        "create_map.save": "Save",
        "create_map.close": "Close",

        # AGV manager
        "agv.title": "AGV Manager",
        "agv.add": "+ Add AGV",
        "agv.modal.add_title": "Add AGV",
        "agv.modal.name": "AGV Name",
        "agv.modal.ip": "IP Address",
        "agv.modal.desc": "Description",
        "agv.modal.cancel": "Cancel",
        "agv.modal.save": "Save",
        "agv.configure": "Configure",
        "agv.delete": "Delete",
        "agv.none": "No AGV available",

        # Task create
        "task_create.left": "Task Group List",
        "task_create.center": "Workflow",
        "task_create.save_workflow": "Save Workflow",
        "task_create.modal.title": "Save Workflow",
        "task_create.modal.name": "Workflow name",
        "task_create.modal.placeholder": "Enter workflow name...",
        "task_create.cancel": "Cancel",
        "task_create.save": "Save",
        "task_create.settings.notify": "Notify Third-Party",
        "task_create.settings.record": "Record Vehicle No.",
        "task_create.settings.unlink": "Unlink rack material or not",
        "task_create.settings.gate": "GateOut/GateIn",
        "task_create.settings.common": "Common",
        "task_create.settings.gatein": "GateIn",
        "task_create.settings.lock": "Lock sign",
        "task_create.settings.unlock": "unLock Pod",
        "task_create.settings.save_task": "Save",
        "wf.remove": "Remove",
        "wf.task_group": "Task Group",
    },
    "vi": {
        "app.title": "TOT ACS",
        "topbar.title": "Hệ thống điều khiển AGV (ACS)",
        "lang.label": "Ngôn ngữ",
        "lang.en": "Tiếng Anh",
        "lang.vi": "Tiếng Việt",
        "account.logout": "Đăng xuất",

        "menu.home": "Trang chủ",
        "menu.map": "Bản đồ",
        "menu.map.create": "Tạo bản đồ",
        "menu.map.configure": "Cấu hình bản đồ",
        "menu.map.agvmap": "AGV Map",
        "menu.task": "Quản lý tác vụ",
        "menu.task.create": "Tạo tác vụ",
        "menu.task.list": "Danh sách tác vụ",
        "menu.agv": "Quản lý AGV",
        "menu.log": "Nhật ký",
        "menu.stat": "Thống kê",
        "menu.help": "Trợ giúp",

        "home.title": "Tổng quan hệ thống",
        "home.card.agv_online": "AGV đang online",
        "home.card.agv_online.desc": "Số AGV đang hoạt động",
        "home.card.tasks_today": "Tác vụ hôm nay",
        "home.card.tasks_today.desc": "Tổng số tác vụ đã chạy",
        "home.card.errors": "Lỗi",
        "home.card.errors.desc": "Sự cố hệ thống đã ghi nhận",
        "home.chart.title": "Phân bố trạng thái tác vụ",
        "home.legend.title": "Trạng thái tác vụ",

        "task_list.title": "Danh sách tác vụ",

        "create_map.toolbox": "Bộ công cụ",
        "create_map.node": "Node",
        "create_map.properties": "Thuộc tính",
        "create_map.zoom": "Thu phóng",
        "create_map.save": "Lưu",
        "create_map.close": "Đóng",

        "agv.title": "Quản lý AGV",
        "agv.add": "+ Thêm AGV",
        "agv.modal.add_title": "Thêm AGV",
        "agv.modal.name": "Tên AGV",
        "agv.modal.ip": "Địa chỉ IP",
        "agv.modal.desc": "Mô tả",
        "agv.modal.cancel": "Hủy",
        "agv.modal.save": "Lưu",
        "agv.configure": "Cấu hình",
        "agv.delete": "Xóa",
        "agv.none": "Chưa có AGV nào",

        "task_create.left": "Danh sách nhóm tác vụ",
        "task_create.center": "Quy trình",
        "task_create.save_workflow": "Lưu quy trình",
        "task_create.modal.title": "Lưu quy trình",
        "task_create.modal.name": "Tên quy trình",
        "task_create.modal.placeholder": "Nhập tên quy trình...",
        "task_create.cancel": "Hủy",
        "task_create.save": "Lưu",
        "task_create.settings.notify": "Thông báo bên thứ ba",
        "task_create.settings.record": "Ghi số xe",
        "task_create.settings.unlink": "Tách vật liệu rack hay không",
        "task_create.settings.gate": "GateOut/GateIn",
        "task_create.settings.common": "Chung",
        "task_create.settings.gatein": "GateIn",
        "task_create.settings.lock": "Khóa biển",
        "task_create.settings.unlock": "Mở khóa Pod",
        "task_create.settings.save_task": "Lưu",
        "wf.remove": "Xóa",
        "wf.task_group": "Nhóm tác vụ",
    },
}

def normalize_lang(lang: str) -> str:
    lang = (lang or "").lower().strip()
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG

def t(lang: str, key: str, default: str | None = None) -> str:
    lang = normalize_lang(lang)
    if key in TRANSLATIONS.get(lang, {}):
        return TRANSLATIONS[lang][key]
    if key in TRANSLATIONS.get("en", {}):
        return TRANSLATIONS["en"][key]
    return default if default is not None else key
