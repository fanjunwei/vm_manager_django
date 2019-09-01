# coding=utf-8
"""
Django settings for vm_manager project.

Generated by 'django-admin startproject' using Django 1.11.2.

For more information on this file, see
https://docs.djangoproject.com/en/1.11/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.11/ref/settings/
"""
import sys
import os

try:
    reload(sys)
    sys.setdefaultencoding('utf-8')
except:
    pass
# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.11/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '5jz2s^_ij_@2c3vzai57d*8($u#qx2%bc^$w)rt&#22!-h1hu2'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_swagger',
    'user_manager',
    'libvirt_manager',
]

MIDDLEWARE = [
    'common.middleware.SessionTransferMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'common.middleware.GlobRequestMiddleware',
    'common.middleware.CorsDomainMiddleware',
]

ROOT_URLCONF = 'vm_manager.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'vm_manager.wsgi.application'

# Database
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators


# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = 'zh-hans'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_L10N = True

USE_TZ = False

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

STATIC_ROOT = os.path.join(BASE_DIR, 'static_all')
STATIC_URL = '/static/'

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'

# **********************************************************
# **          Django REST framework Config                **
# **********************************************************
REST_FRAMEWORK = {
    "DATETIME_FORMAT": "%Y-%m-%d %H:%M:%S",
    "DATETIME_INPUT_FORMATS": ["%Y-%m-%d %H:%M:%S"],
    'EXCEPTION_HANDLER': 'common.utils.rest_exception_handler',
    'DEFAULT_PAGINATION_CLASS': 'common.pagination.LimitOffsetAndAllPagination',
    'DEFAULT_FILTER_BACKENDS': (
        'common.filters.OrderingFilter',  # ordering=account,-username
        'common.filters.SearchFilter',  # ?search=xxx
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'common.authentication.CsrfExemptSessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
        # 'rest_framework.permissions.AllowAny',
    ),
}

# **********************************************************
# **                   自定义配置                          **
# **********************************************************
LIBVIRT_URI = 'qemu+ssh://root@192.168.17.30/system?socket=/var/run/libvirt/libvirt-sock'
VM_BASE_DISKS_DIR = '/Users/fanjunwei/Documents/workspace/vm_manager/assets'
VM_DATA_DIR = '/Users/fanjunwei/Documents/workspace/vm_manager/data'
