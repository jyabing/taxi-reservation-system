# === 一键修复 vehicles 迁移断链 ===
set -e

APP=vehicles
MIGDIR="$APP/migrations"

# 0) 确保在项目根目录
test -f manage.py || { echo "请在包含 manage.py 的目录运行"; exit 1; }

# 1) 找到 <0006 的最后一条迁移（如 0005_xxx 或 0004_xxx... 如果都没有就取 0001_initial）
prev=$(
  ls "$MIGDIR"/0[0-9][0-9]_*.py 2>/dev/null \
  | sed -E 's|.*/||' \
  | sort -V \
  | awk '$1 < "0006_" { print }' \
  | tail -n1 \
  | sed 's/\.py$//'
)

# 兜底：若没找到（比如只有 0001/0002），就取 0001_*.py
if [ -z "$prev" ]; then
  prev=$(ls "$MIGDIR"/0001_*.py 2>/dev/null | sed -E 's|.*/||' | sed 's/\.py$//' | head -n1)
fi

if [ -z "$prev" ]; then
  echo "没有找到任何可作为依赖的迁移文件（$MIGDIR/0001_*.py 也不存在），请检查项目。"
  exit 1
fi

echo "将把 0006 依赖设置为：$prev"

# 2) 生成/覆盖 占位 0006
cat > "$MIGDIR/0006_map_old_reservation_statuses.py" <<PY
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('$APP', '$prev'),
    ]

    operations = []
PY

echo "已写入 $MIGDIR/0006_map_old_reservation_statuses.py"

# 3) 先把 0006 标记为已应用（不执行任何操作），再整体迁移
python manage.py migrate $APP 0006 --fake
python manage.py migrate

# 4) 自检
python manage.py check

echo "✅ 修复完成：迁移链已闭合。"
