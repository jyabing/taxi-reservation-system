import os

driver = getattr(request.user, "driver_profile", None)
if not driver:
    return render(request, 'accounts/profile_error.html', {'message': '未绑定司机资料，请联系管理员'})
TARGET = 'driver=driver'
REPLACEMENT = '''driver = getattr(request.user, "driver_profile", None)
if not driver:
    return render(request, 'accounts/profile_error.html', {'message': '未绑定司机资料，请联系管理员'})
'''

def replace_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    modified = False
    new_lines = []
    for line in lines:
        if TARGET in line:
            indent = line[:len(line) - len(line.lstrip())]
            new_lines.append(f"{indent}{REPLACEMENT}")
            new_lines.append(f"{indent}{line.replace(TARGET, 'driver=driver')}")
            modified = True
        else:
            new_lines.append(line)

    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"✅ Replaced in {filepath}")

def scan_folder(folder):
    for root, _, files in os.walk(folder):
        for file in files:
            if file.endswith('.py'):
                replace_in_file(os.path.join(root, file))

# 用法：替换当前目录下所有 Python 文件
scan_folder('.')
