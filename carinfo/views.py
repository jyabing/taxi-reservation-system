import datetime, openpyxl
from datetime import date
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import get_template
from accounts.utils import check_module_permission
from vehicles.models import Reservation
from .models import Car
from .forms import CarForm

import datetime
from carinfo.services.car_access import get_car_by_id 


@login_required
@check_module_permission('carinfo')
def car_list(request):
    today = date.today()
    cars = Car.objects.all()
    cars_enriched = []

    for car in cars:
        car_age = today.year - car.year if car.year else None
        inspection_cycle = "未知"
        next_inspection = None
        inspection_warning = False

        if car.first_registration_date:
            years_since_first = today.year - car.first_registration_date.year
            if years_since_first < 6:
                inspection_cycle = "前6年每2年"
                next_inspection = car.first_registration_date.replace(year=car.first_registration_date.year + 2)
            else:
                inspection_cycle = "每年一次"
                if car.inspection_date:
                    next_inspection = car.inspection_date.replace(year=car.inspection_date.year + 1)

        if next_inspection and next_inspection <= today:
            inspection_warning = True

        cars_enriched.append({
            'obj': car,
            'car_age': car_age,
            'inspection_cycle': inspection_cycle,
            'next_inspection': next_inspection,
            'inspection_warning': inspection_warning,
        })

    return render(request, 'carinfo/car_list.html', {
        'cars': cars_enriched,
        'request': request,
    })

@login_required
@check_module_permission('carinfo')
def car_detail(request, pk):
    car = get_car_by_id(pk)

    # ✅ 车龄
    current_year = datetime.date.today().year
    car_age = current_year - car.year if car.year else None

    # ✅ 年检周期与下次年检推测
    next_inspection = None
    inspection_cycle = "未知"

    if car.first_registration_date:
        years_since_first = current_year - car.first_registration_date.year

        if years_since_first < 6:
            next_inspection = car.first_registration_date.replace(year=car.first_registration_date.year + 2)
            inspection_cycle = "前6年每2年"
        else:
            if car.inspection_date:
                next_inspection = car.inspection_date.replace(year=car.inspection_date.year + 1)
            inspection_cycle = "每年一次"

    return render(request, 'carinfo/car_detail.html', {
        'car': car,
        'car_age': car_age,
        'next_inspection': next_inspection,
        'inspection_cycle': inspection_cycle,
    })


# ✅ 编辑车辆视图
@login_required
@check_module_permission('carinfo')
def car_edit(request, pk):
    car = get_object_or_404(Car, pk=pk)

    if request.method == 'POST':
        form = CarForm(request.POST, request.FILES, instance=car)
        if form.is_valid():
            form.save()
            return redirect('carinfo:car_list')
    else:
        form = CarForm(instance=car)

    return render(request, 'carinfo/car_form.html', {
        'form': form,
        'car': car,
    })

@login_required
@check_module_permission('carinfo')
def car_delete(request, pk):
    car = get_object_or_404(Car, pk=pk)

    if request.method == 'POST':
        car.delete()
        messages.success(request, f"已删除车辆：{car.license_plate}")
        return redirect('carinfo:car_list')

    return render(request, 'carinfo/car_confirm_delete.html', {
        'car': car,
    })


# ✅ 创建车辆视图
@login_required
@check_module_permission('carinfo')
def car_create(request):
    if request.method == 'POST':
        form = CarForm(request.POST, request.FILES)
        if form.is_valid():
            car = form.save()
            return redirect('carinfo:car_list')
    else:
        form = CarForm()
        car = None

    return render(request, 'carinfo/car_form.html', {
        'form': form,
        'car': car,
    })

# ✅ 导出车辆台账为Excel
@login_required
@check_module_permission('carinfo')
def export_car_list_excel(request):
    today = date.today()
    cars = Car.objects.all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "车辆台账"

    headers = [
        "车牌号", "车辆名称", "品牌", "型号", "出厂年份", "车龄", "燃料类型", "颜色",
        "车辆状态", "是否启用", "里程", "年检周期", "下次年检", "保险到期日", "车检到期日",
        "负责人", "联系电话", "部门", "ETC编号", "油卡号", "刷卡机编号", "GPS编号",
        "备注"
    ]
    ws.append(headers)

    for car in cars:
        car_age = today.year - car.year if car.year else None

        inspection_cycle = "未知"
        next_inspection = None
        if car.first_registration_date:
            if today.year - car.first_registration_date.year < 6:
                inspection_cycle = "前6年每2年"
                next_inspection = car.first_registration_date.replace(year=car.first_registration_date.year + 2)
            else:
                inspection_cycle = "每年一次"
                if car.inspection_date:
                    next_inspection = car.inspection_date.replace(year=car.inspection_date.year + 1)

        ws.append([
            car.license_plate,
            car.name,
            car.brand,
            car.model,
            car.year,
            car_age,
            car.fuel_type,
            car.color,
            car.get_status_display(),
            "是" if car.is_active else "否",
            car.mileage,
            inspection_cycle,
            next_inspection,
            car.insurance_expiry,
            car.inspection_date,
            car.manager_name,
            car.manager_phone,
            car.department,
            car.etc_device,
            car.fuel_card_number,
            car.pos_terminal_id,
            car.gps_device_id,
            car.notes,
        ])

    # 设置样式
    for col in ws.columns:
        for cell in col:
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[col[0].column_letter].width = 16
    for cell in ws[1]:
        cell.font = Font(bold=True)

    response = HttpResponse(
        content=openpyxl.writer.excel.save_virtual_workbook(wb),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = f'attachment; filename=车辆台账_{today}.xlsx'
    return response

# ✅ 车辆详情弹窗视图（用于Ajax模态框）
@login_required
#check_module_permission('carinfo')
def car_detail_modal(request, pk):
    print(f"[DEBUG] Ajax 请求收到，车辆 ID：{pk}")  # ✅ 后台调试用

    # ✅ 尝试加载模板，确认是否能找到
    try:
        template = get_template('carinfo/car_detail_modal.html')
        print('[TEMPLATE FOUND] 模板已找到：carinfo/car_detail_modal.html')
    except Exception as e:
        print('[TEMPLATE ERROR] 模板无法找到：', e)


    car = get_object_or_404(Car, pk=pk)

    current_year = datetime.date.today().year
    car_age = current_year - car.year if car.year else None

    next_inspection = None
    inspection_cycle = "未知"

    if car.first_registration_date:
        years_since_first = current_year - car.first_registration_date.year
        if years_since_first < 6:
            next_inspection = car.first_registration_date.replace(year=car.first_registration_date.year + 2)
            inspection_cycle = "前6年每2年"
        else:
            if car.inspection_date:
                next_inspection = car.inspection_date.replace(year=car.inspection_date.year + 1)
            inspection_cycle = "每年一次"

    # ✅ 权限判断：只有管理员或有权限者能看到管理信息
    show_management = request.user.is_superuser or request.user.has_perm("carinfo.view_management_info")

    # ✅ 追加：最近预约记录
    recent_reservations = Reservation.objects.filter(
        vehicle=car
    ).select_related('driver').order_by('-start_time')[:5]

    return render(request, 'carinfo/car_detail_modal.html', {
        'car': car,
        'car_age': car_age,
        'next_inspection': next_inspection,
        'inspection_cycle': inspection_cycle,
        'show_management': show_management,
        'recent_reservations': recent_reservations,  # ✅ 传给模板
})