from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.utils import check_module_permission
from .models import Car
from .forms import CarForm

@login_required
@check_module_permission('carinfo')
def car_list(request):
    cars = Car.objects.all()
    return render(request, 'carinfo/car_list.html', {'cars': cars})

@login_required
@check_module_permission('carinfo')
def car_detail(request, pk):
    car = get_object_or_404(Car, pk=pk)
    return render(request, 'carinfo/car_detail.html', {'car': car})

@login_required
@check_module_permission('carinfo')
def car_create(request):
    if request.method == 'POST':
        form = CarForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "车辆已成功添加")
            return redirect('carinfo:car_list')
    else:
        form = CarForm()
    return render(request, 'carinfo/car_form.html', {'form': form})

@login_required
@check_module_permission('carinfo')
def car_edit(request, pk):
    car = get_object_or_404(Car, pk=pk)
    if request.method == 'POST':
        form = CarForm(request.POST, instance=car)
        if form.is_valid():
            form.save()
            messages.success(request, "车辆信息已更新")
            return redirect('carinfo:car_list')
    else:
        form = CarForm(instance=car)
    return render(request, 'carinfo/car_form.html', {'form': form, 'car': car})

@login_required
@check_module_permission('carinfo')
def car_delete(request, pk):
    car = get_object_or_404(Car, pk=pk)
    if request.method == 'POST':
        car.delete()
        messages.success(request, "车辆已删除")
        return redirect('carinfo:car_list')
    return render(request, 'carinfo/car_confirm_delete.html', {'car': car})