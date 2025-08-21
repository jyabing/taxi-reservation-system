import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # 读取 .env
BASE_DIR = Path(__file__).resolve().parent.parent

STATIC_URL = '/static/'
STATICFILES_DIRS = [ BASE_DIR / 'static' ]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',  # ✅ 放在最上面！
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'common.middleware.LinkClickTrackerMiddleware', # ✅ 添加链接点击跟踪中间件
    'common.middleware.NavigationUsageMiddleware', # ✅ 添加导航使用情况中间件
]


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True   # 仅用于开发环境
#DEBUG = False 

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "taxi-reservation-system.onrender.com",  # 保留 Render
    ".onrender.com",                         # 保留 Render 子域
    "tms-japan.com",                         # 你的独立域名
    "www.tms-japan.com",                     # 带 www 的域名
    # 未来公司域名，等你启用时再加：
    "hikarikoutsu.com",
    "www.hikarikoutsu.com",
    #"honntenn.com",
    #"www.honntenn.com",
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # 你的 app
    'accounts.apps.AccountsConfig',  # ✅ 保留这个
    'vehicles',        # ✅ 自主配车系统（原 reservation）：预约、审批、出入库等
    'rangefilter',
    'staffbook',        # ✅ 员工系统：人事台账、保险、资格证等
    'dailyreport',     # ✅ 日报系统：乘务日报、统计、明细、出勤、分析
    'carinfo',          # ✅ 车辆管理系统：台账、维修、照片等
    'admin_tools',       # ✅ 管理工具：系统备份
    'common',            # ✅ 公共模块：工具函数、常量等
    'django.contrib.humanize',
    'widget_tweaks',
]


ROOT_URLCONF = 'fleet_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        #'DIRS': [],
        'DIRS': [BASE_DIR / 'templates'],  # 告诉 Django 去哪里找 templates
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug', # ✅ 添加调试处理器
                'django.template.context_processors.request',
                'django.template.context_processors.csrf',
                'django.contrib.auth.context_processors.auth', 
                'django.contrib.messages.context_processors.messages', # ✅ 添加消息处理器
                'common.context_processors.common_links',  # ✅ 添加公共链接处理器
                
            ],
        },
    },
]

WSGI_APPLICATION = 'fleet_project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

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

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'zh-hans'

#TIME_ZONE = 'UTC'
TIME_ZONE = 'Asia/Tokyo'  # 改为东京时区会更合适

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.DriverUser'

LOGIN_URL = '/accounts/login/'

# =========================
# ✅ 邮件发送设置（模块10）
# =========================

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'           # 📮 例如：smtp.gmail.com / smtp.qq.com
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = 'jiabing.msn@gmail.com'        # 发件人邮箱
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')       # 邮箱“应用密码”或授权码
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# ✅ 新增以下两行 👇
DEFAULT_NOTIFICATION_EMAIL = EMAIL_HOST_USER
SITE_BASE_URL = 'https://taxi-reservation.onrender.com/'   # ⛳ 请改为你真实上线网址

LOGIN_REDIRECT_URL = '/accounts/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/success/'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
#MEDIA_ROOT = '/media/'

DATE_FORMAT = "Y-m-d"            # 例如：2025-05-08
TIME_FORMAT = "H:i"              # 例如：14:30
DATETIME_FORMAT = "Y-m-d H:i"    # 例如：2025-05-08 14:30

USE_L10N = False  # 禁用本地化，以便使用上面自定义格式

LEDGER_API_HOST = os.getenv('LEDGER_API_HOST', 'taxi-reservation.onrender.com')

DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000