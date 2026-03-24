from django.contrib import admin  # Importamos o admin padrão do Django
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.views.generic.base import RedirectView
from django.contrib.auth import views as auth_views

# Removi a importação do admin_site customizado que estava bloqueando o Unfold

urlpatterns = [
    # ---------------------------------------------------------
    # RECUPERAÇÃO DE SENHA (Customizada)
    # ---------------------------------------------------------
    path('password_reset/', auth_views.PasswordResetView.as_view(
        template_name='home/password_reset.html',
        # Esta linha abaixo é a mágica que remove o e-mail feio:
        html_email_template_name='emails/password_reset_html_email.html',
        subject_template_name='emails/password_reset_subject.txt'
    ), name='password_reset'),

    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='home/password_reset_done.html'
    ), name='password_reset_done'),

    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='home/password_reset_confirm.html'
    ), name='password_reset_confirm'),

    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='home/password_reset_complete.html'
    ), name='password_reset_complete'),

    # ---------------------------------------------------------
    # APP PRINCIPAL E ADMIN (CORRIGIDO PARA UNFOLD)
    # ---------------------------------------------------------
    path('', include('home.urls')),

    # Mudamos admin_site.urls para admin.site.urls
    path('admin/', admin.site.urls),

    path('favicon.ico', RedirectView.as_view(
        url=settings.STATIC_URL + 'img/favicon.ico')),
]

# ---------------------------------------------------------
# TRATAMENTO DE MÍDIA E STATIC
# ---------------------------------------------------------
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
    }),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL,
                          document_root=settings.STATIC_ROOT)
