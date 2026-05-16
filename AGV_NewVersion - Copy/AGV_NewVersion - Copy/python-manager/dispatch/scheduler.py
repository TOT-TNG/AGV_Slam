"""
dispatch/scheduler.py  — Scheduler tự động
-------------------------------------------
Migrate từ main.py:
  - run_scheduler()    (lines ~1492–1531)
"""
from __future__ import annotations
import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AppContext


class Scheduler:
    """
    Quản lý lịch vận chuyển hàng ngày và tự động dispatch mission khi đến giờ.
    """

    def __init__(self, ctx: AppContext):
        self.ctx      = ctx
        self._running = False

    def run(self):
        """
        Kiểm tra thời biểu và dispatch mission khi đến giờ.
        Bước 1: Khi đúng giờ → đánh dấu 'triggered'.
        Bước 2: Với task 'triggered' → kiểm tra AGV sẵn sàng, nếu có thì dispatch.
        Gọi lặp mỗi 10s từ GUI (app.after(10000, ...)).
        """
        ctx    = self.ctx
        config = ctx.config
        now    = datetime.datetime.now()
        current_time_str = now.strftime("%H:%M")

        tasks          = config.get('schedule_tasks', [])
        config_changed = False

        for task in tasks:
            # Bước 1: pending → triggered khi đúng giờ
            if task['status'] == 'pending' and task['time'] == current_time_str:
                print(f"SCHEDULER: Time matched for task at {task['time']} → Team {task['target']}. "
                      f"Marking as triggered.")
                task['status']  = 'triggered'
                config_changed  = True

            # Bước 2: dispatch khi có AGV rảnh
            if task['status'] == 'triggered':
                any_free = any(
                    agv.action_info == "idle"
                    and agv.task_lifecycle == "free"
                    and agv.error_code == 0
                    for agv in ctx.agv_list
                )
                if any_free:
                    print(f"SCHEDULER: AGV available. Dispatching triggered task → Team {task['target']}")
                    request_handler = getattr(ctx, 'request_handler', None)
                    if request_handler:
                        request_handler.add_to_queue(task['target'])
                    task['status']  = 'executed'
                    config_changed  = True
                else:
                    print(f"SCHEDULER: No AGV available for task at {task['time']}. Will retry...")

        if config_changed:
            from config_mgmt.settings_io import save_config
            save_config(config)

    def stop(self):
        self._running = False
