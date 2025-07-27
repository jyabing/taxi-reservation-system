# carinfo/services/car_flags.py

def is_retired(car):
    """
    判断车辆是否已报废
    """
    return car.status == 'retired'

def is_under_repair(car):
    """
    判断车辆是否正在维修中
    """
    return car.status == 'repair'

def is_reserved_by_admin(car):
    """
    判断车辆是否仅管理员可预约
    """
    return getattr(car, 'is_reserved_only_by_admin', False)

def is_admin_only(car):
    """
    判断车辆是否为“调配用车”：
    可用状态 + 限管理员预约
    """
    return car.status == 'available' and is_reserved_by_admin(car)
