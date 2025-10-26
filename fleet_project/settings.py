# settings.py 头部
from pathlib import Path
import os
BASE_DIR = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")  # 确保先加载 .env


# =========================
# 静态文件设置
# =========================
STATIC_URL = '/static/'
STATICFILES_DIRS = [ BASE_DIR / 'static' ]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # ========== [BEGIN INSERT LINE M2] ==========
    'common.middleware.SystemClosedMiddleware',     # 🔒 全站拦截（非管理员 → /closed/）
    # ========== [END INSERT LINE M2] ==========
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'common.middleware.LinkClickTrackerMiddleware',
    'common.middleware.NavigationUsageMiddleware',
]


# =========================
# 安全配置
# =========================
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = True   # 开发环境
#DEBUG = False  # 上线时关掉

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "taxi-reservation-system.onrender.com",
    ".onrender.com",
    "tms-japan.com",
    "www.tms-japan.com",
    "hikarikoutsu.com",
    "www.hikarikoutsu.com",
    # "honntenn.com",
    # "www.honntenn.com",
]

# =========================
# 应用
# =========================
INSTALLED_APPS = [
    # 系统自带
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # 你的 app
    'accounts.apps.AccountsConfig',
    'vehicles.apps.VehiclesConfig',
    'dailyreport.apps.DailyreportConfig',
    'rangefilter',
    'staffbook',
    'carinfo',
    'admin_tools',
    'common',
    'django.contrib.humanize',
    'widget_tweaks',

    # 新增
    'storages',   # ✅ Cloudflare R2
    "django_extensions",
]

ROOT_URLCONF = 'fleet_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.csrf',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'common.context_processors.common_links',
            ],
        },
    },
]

WSGI_APPLICATION = 'fleet_project.wsgi.application'

# =========================
# 数据库
# =========================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'postgres'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASS'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# =========================
# 密码验证
# =========================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =========================
# 国际化
# =========================
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_TZ = True

# =========================
# 默认主键类型
# =========================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.DriverUser'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/accounts/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/success/'

# =========================
# 邮件设置
# =========================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'jiabing.msn@gmail.com'
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
DEFAULT_NOTIFICATION_EMAIL = EMAIL_HOST_USER
SITE_BASE_URL = 'https://taxi-reservation.onrender.com/'  # 请改为真实上线网址


# =========================
# 其他
# =========================
# 本地 media 设置留空（R2 不使用本地 MEDIA_ROOT）
MEDIA_URL = '/media/'
MEDIA_ROOT = ""

DATE_FORMAT = "Y-m-d"
TIME_FORMAT = "H:i"
DATETIME_FORMAT = "Y-m-d H:i"
USE_L10N = False

LEDGER_API_HOST = os.getenv('LEDGER_API_HOST', 'taxi-reservation.onrender.com')

DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

# =========================
# Cloudflare R2 存储（稳定做法）
# =========================
from .settings_storage import *  # Cloudflare R2

# --- System Maintenance Switch (ENV-driven) ---
# 在 .env 里写：SYSTEM_CLOSED=True 或 False
SYSTEM_CLOSED = os.getenv("SYSTEM_CLOSED", "True") == "True"

# ========== [BEGIN INSERT BLOCK S1] ==========
# 暂停营业时仍然允许访问的 URL 前缀（未登录用户也放行）
SYSTEM_CLOSED_ALLOWLIST_PREFIXES = [
    "/closed/",
    "/accounts/login/",
    "/accounts/logout/",
    "/accounts/password_reset",
    "/accounts/password_change",
    STATIC_URL.rstrip("/"),
    (MEDIA_URL.rstrip("/") if MEDIA_URL else "/media"),
    "/admin/login/",
]
# ========== [END INSERT BLOCK S1] ==========