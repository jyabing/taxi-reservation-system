from apscheduler.schedulers.background import BackgroundScheduler
from .tasks import auto_update_reservations

def start():
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_update_reservations, 'interval', minutes=30)
    scheduler.start()