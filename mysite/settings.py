import logging
import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=None):
    value = os.getenv(name, "")
    if value:
        return [item.strip() for item in value.split(",") if item.strip()]
    return list(default or [])

# -----------------------------
# SEGURANÇA
# -----------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
DEBUG = env_bool("DEBUG", True)

# Domínios autorizados
default_allowed_hosts = [
    "localhost",
    "127.0.0.1",
    "odontoclinics.com",
    "www.odontoclinics.com",
    "mysite-100d.onrender.com",
]
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", default_allowed_hosts)

RENDER_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_HOSTNAME)

default_csrf_trusted_origins = [
    "https://odontoclinics.com",
    "https://www.odontoclinics.com",
    "https://mysite-100d.onrender.com",
]
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", default_csrf_trusted_origins)

if RENDER_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOSTNAME}")

# Configurações de Cookies e Headers de Proxy (VITAL para o Render)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Isso aqui diz ao Django para confiar no HTTPS que o Render fornece
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG


# -----------------------------
# APPS
# -----------------------------
INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",  # Movi para cá (antes do admin)
    "unfold.contrib.import_export",
    "unfold.contrib.guardian",
     
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    'import_export',
    'home.apps.HomeConfig',
]

# -----------------------------
# MIDDLEWARE
# -----------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Multi-tenant / clínica
    'home.middleware.ClinicaMiddleware',
]


ROOT_URLCONF = 'mysite.urls'


# -----------------------------
# TEMPLATES
# -----------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                # Removida a linha configuracao_context que causava o erro
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                

                # Esta é a sua função unificada que resolve tudo de uma vez
                'home.context_processors.clinica_context',
            ],
        },
    },
]


WSGI_APPLICATION = 'mysite.wsgi.application'


# -----------------------------
# BANCO DE DADOS
# -----------------------------
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        ssl_require=env_bool("DATABASE_SSL_REQUIRE", bool(RENDER_HOSTNAME)),
    )
}


# -----------------------------
# VALIDAÇÃO DE SENHA
# -----------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# -----------------------------
# INTERNACIONALIZAÇÃO
# -----------------------------
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'

USE_I18N = True
USE_TZ = True


# -----------------------------
# ARQUIVOS ESTÁTICOS
# -----------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'home' / 'static',
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# -----------------------------
# ARQUIVOS DE MÍDIA
# -----------------------------
MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "/data/media" if RENDER_HOSTNAME or not DEBUG else BASE_DIR / "media"))


# -----------------------------
# LOGGING (Mantive exatamente como estava no seu original)
# -----------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR' if DEBUG else 'WARNING',
        },
        'home': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
    },
}


# -----------------------------
# AUTENTICAÇÃO
# -----------------------------
LOGIN_REDIRECT_URL = '/index/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/login/'


# -----------------------------
# CONFIGURAÇÃO DE NEGÓCIO
# -----------------------------
PLANOS_CONFIG = {
    'essential': {'preco': 99.00},      # Ajuste os valores conforme seu modelo
    'professional': {'preco': 199.00},
}


# -----------------------------
# Integração com Google Calendar
# -----------------------------
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")


UNFOLD = {
    "SITE_TITLE": "OdontoClinics",
    "SITE_HEADER": "Painel de Controle SaaS",
    "SITE_SYMBOL": "dentistry",
    "STYLES": [
        lambda request: "https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@48,400,1,0",
    ],
    "SHOW_HISTORY": True,
    "COLORS": {
        "primary": {
            "50": "230, 247, 253",  # Seu --tema-claro
            "100": "204, 239, 251",
            "200": "166, 227, 248",
            "300": "115, 211, 244",
            "400": "65, 192, 237",
            "500": "37, 170, 226",  # Cor Principal #25AAE2 🚀
            "600": "27, 139, 189",  # Seu --tema-escuro
            "700": "22, 111, 151",
            "800": "19, 94, 127",
            "900": "16, 77, 104",
            "950": "11, 50, 68",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
    },
    "DASHBOARD": {
        "show_all_applications": True, 
        "navigation": [
            {
                "title": "Navegação Principal",
                "separator": True,
                "items": [
                    {
                        "title": "Dashboard",
                        "icon": "dashboard",
                        "link": "admin:index",
                    },
                ],
            },
        ],
        "widgets": [
            {
                "wrapper_class": "col-span-12",
                "widget_class": "home.widgets.FaturamentoSaaSWidget",
            },
            {
                "wrapper_class": "col-span-12 lg:col-span-6",
                "widget_class": "home.widgets.FaturamentoPrevistoWidget",
            },
            {
                "wrapper_class": "col-span-12 lg:col-span-6",
                "widget_class": "home.widgets.TotalClinicasWidget",
            },
            {
                "wrapper_class": "col-span-12 lg:col-span-6",
                "widget_class": "home.widgets.CrescimentoPacientesWidget",
            },
            {
                "wrapper_class": "col-span-12 lg:col-span-6",
                "widget_class": "home.widgets.ConsultasHojeWidget",
            },
            {
                "wrapper_class": "col-span-12 lg:col-span-6",
                "widget_class": "home.widgets.FaturamentoMensalWidget",
            },
        ],
    },
}

# --- CONFIGURAÇÃO DE E-MAIL PARA MAILGUN ---
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.mailgun.org"
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True

    # ATENÇÃO: Mudei de 'postmaster' para 'suporte' conforme sua screenshot
    EMAIL_HOST_USER = "suporte@mg.odontoclinics.com"
    
    # Verifique se no Render a chave é MAILGUN_SMTP_PASSWORD
    EMAIL_HOST_PASSWORD = os.getenv("MAILGUN_SMTP_PASSWORD")

    DEFAULT_FROM_EMAIL = "OdontoClinics <suporte@odontoclinics.com>"
    SERVER_EMAIL = "suporte@mg.odontoclinics.com"



# -----------------------------
# MERCADO PAGO (PRODUÇÃO)
# -----------------------------
# Pega o Access Token das variáveis de ambiente do Render
MERCADO_PAGO_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")

# Caso queira usar a Public Key no front-end via context processor depois
MERCADO_PAGO_PUBLIC_KEY = "APP_USR-909cc07b-ca8e-42dd-a164-11a3eb264460"

