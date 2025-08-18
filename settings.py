"""
oTree settings for Spaceship Coordination Experiment
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'otree',
    'channels',
    'spaceship_coordination',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
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
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JS, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# oTree settings
OTREE_APPS = [
    'spaceship_coordination',
]

OTREE_PRODUCTION = not DEBUG

# oTree session configuration
SESSION_CONFIGS = [
    {
        'name': 'spaceship_coordination',
        'display_name': 'Spaceship Coordination Experiment',
        'app_sequence': ['spaceship_coordination'],
        'num_demo_participants': 3,
    },
]

SESSION_CONFIG_DEFAULTS = {
    'real_world_currency_per_point': 1.00,
    'participation_fee': 5.00,
    'doc': 'Spaceship Coordination Experiment',
}

# Channels configuration for WebSocket support
ASGI_APPLICATION = 'asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [os.environ.get('REDIS_URL', 'redis://localhost:6379')],
        },
    },
}

# Redis configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

# Experiment configuration
EXPERIMENT_CONFIG = {
    'PU_PER_ROUND': 4,
    'TRAVEL_COSTS': {
        'Alpha': 0,
        'Beta': 1,
        'Gamma': 2,
        'Omega': 3,
    },
    'PROBE_COST': 1,
    'ROBOT_COST': 1,
    'MINE_SHALLOW_COST': 1,
    'MINE_DEEP_COST': 2,
    'BRIEFING_HIGH_PRESSURE': 90,
    'BRIEFING_LOW_PRESSURE': 180,
    'ACTION_STAGE_TIME': 15,
    'RESULT_STAGE_TIME': 15,
    'DEFAULT_PROBABILITY_MATRIX': {
        'shallow': {
            'none': 0.15,
            'probe_only': 0.35,
            'robot_only': 0.30,
            'probe_plus_robot': 0.55,
        },
        'deep': {
            'none': 0.30,
            'robot_only': 0.50,
            'probe_only': 0.55,
            'probe_plus_robot': 0.80,
        }
    },
    'PARTIAL_YIELD_RANGE': (0.30, 0.80),
    'GUARANTEED_PAYMENT': '£5.00',
    'BONUS_MAX': '£3.00',
    'GRACE_PERIOD': 90,  # seconds for disconnect handling
}

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'spaceship_coordination.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}

# Create logs directory if it doesn't exist
os.makedirs(BASE_DIR / 'logs', exist_ok=True)


