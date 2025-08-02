# carinfo/services/car_access.py

from carinfo.models import Car
from django.shortcuts import get_object_or_404

def get_car_by_id(car_id):
    """根据车辆 ID 获取车辆对象"""
    return Car.objects.filter(id=car_id).first()

def get_all_active_cars():
    """获取所有非报废车辆"""
    return Car.objects.exclude(status='retired')

def get_car_license_plate(car_id):
    """根据 ID 获取车牌号"""
    car = get_car_by_id(car_id)
    return car.license_plate if car else ''

def is_car_reservable(car):
    """
    判断车辆是否允许预约：
    排除状态为报废 retired、维修中 under_repair 的车辆
    """
    return car.status == 'usable' and not car.is_reserved_only_by_admin

def is_under_repair(car):
    return car.status == 'repair'

def is_retired(car):
    return car.status == 'retired'