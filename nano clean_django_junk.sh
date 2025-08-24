#!/bin/bash

echo "🧹 开始清理 Django 项目中的垃圾和残留文件..."

# 删除所有 .bak 文件
find . -name "*.bak" -type f -print -delete

# 删除所有 .pyc 文件
find . -name "*.pyc" -type f -print -delete

# 删除所有 __pycache__ 文件夹
find . -name "__pycache__" -type d -print -exec rm -r {} +

# 删除所有 migrations 中非 __init__.py 文件
find . -path "*/migrations/*.py" ! -name "__init__.py" -print -delete
find . -path "*/migrations/*.pyc" -print -delete

echo "✅ 清理完毕！你现在的项目干净得像新洗的裤衩 🚿"
