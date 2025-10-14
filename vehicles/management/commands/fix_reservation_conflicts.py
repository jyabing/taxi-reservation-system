# vehicles/management/commands/fix_reservation_conflicts.py
from django.core.management.base import BaseCommand
from vehicles.utils.conflict_fix import find_and_fix_conflicts

class Command(BaseCommand):
    help = "检测并修复重复预约（同车同时间段不同司机）。默认仅预览，可加 --commit 实际执行。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="实际修改数据库（默认仅预览）。"
        )

    def handle(self, *args, **options):
        commit = options["commit"]
        self.stdout.write("🚗 正在扫描车辆预约冲突...\n")

        # ✅ 调用共用逻辑
        result = find_and_fix_conflicts(commit=commit)

        self.stdout.write(f"共检测到冲突对数：{result['conflicts']}")
        if commit:
            self.stdout.write(f"已自动取消较晚创建的预约：{result['fixed']} 条。")
        else:
            self.stdout.write("当前为 Dry-Run 预览模式，未修改数据库。")

        # ✅ 输出样本（最多 50 条）
        if result["samples"]:
            self.stdout.write("\n示例记录（最多 50 条）：")
            for s in result["samples"]:
                self.stdout.write(
                    f"- 车辆: {s['vehicle']}, 日期: {s['date']}, "
                    f"司机1={s['driver1']}, 司机2={s['driver2']}, "
                    f"时间={s['time']}, "
                    f"保留ID={s['winner_id']}, "
                    f"{'已取消' if commit else '将取消'}ID={s['canceled_id'] or '(预览)'}"
                )
        else:
            self.stdout.write("\n未检测到冲突。")

        self.stdout.write("\n✅ 执行完毕。")
