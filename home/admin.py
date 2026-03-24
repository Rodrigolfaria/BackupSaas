from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from unfold.admin import ModelAdmin
from unfold.sites import UnfoldAdminSite
from unfold.contrib.import_export.forms import ExportForm, ImportForm

try:
    from .widgets import (
        FaturamentoSaaSWidget,
        TotalClinicasWidget,
        FaturamentoMensalWidget,
        CrescimentoPacientesWidget,
        ConsultasHojeWidget,
        FaturamentoPrevistoWidget
    )
    print("✅ Widgets carregados com sucesso!")
except Exception as e:
    print(f"❌ Erro ao carregar widgets: {e}")

from .models import (
    Clinic, Profile, Paciente, Consulta,
    Financeiro, Configuracao, ConfiguracaoWhatsApp, LembreteLog
)
from .resources import ConsultaResource, PacienteResource

# -------------------------------------------------------------------------
# CONFIGURAÇÃO DO SITE ADMIN (MANTENDO SUA ESTRUTURA)
# -------------------------------------------------------------------------


class MyAdminSite(UnfoldAdminSite):
    site_header = "Painel de Controle SaaS"
    site_title = "OdontoClinics Admin"

    def get_dashboard_widgets(self, request):
        """
        Retorna a lista de INSTÂNCIAS dos widgets. 
        O Unfold precisa das classes aqui para renderizar na index.
        """
        return [
            FaturamentoSaaSWidget,
            FaturamentoMensalWidget,
            TotalClinicasWidget,
            CrescimentoPacientesWidget,
            ConsultasHojeWidget,
            FaturamentoPrevistoWidget,
        ]

    def index(self, request, extra_context=None):
        if extra_context is None:
            extra_context = {}

        # Injeta os widgets no contexto da página inicial do admin
        extra_context.update({
            "dashboard_widgets": self.get_dashboard_widgets(request)
        })
        return super().index(request, extra_context=extra_context)


admin_site = MyAdminSite(name="admin_site")

# -----------------------------
# CLINIC (TENANT)
# -----------------------------


@admin.register(Clinic)
class ClinicAdmin(ModelAdmin):
    list_display = ('nome', 'plano', 'telefone', 'criado_em')
    search_fields = ('nome', 'telefone')
    list_filter = ('plano', 'criado_em')

# -----------------------------
# CONFIGURAÇÃO DE WHATSAPP
# -----------------------------


@admin.register(ConfiguracaoWhatsApp)
class ConfiguracaoWhatsAppAdmin(ModelAdmin):
    list_display = ('clinic', 'instancia_nome', 'status_conexao',
                    'lembretes_ativos', 'tipo_envio')
    list_editable = ('lembretes_ativos', 'tipo_envio')
    list_filter = ('lembretes_ativos', 'status_conexao', 'tipo_envio')
    search_fields = ('clinic__nome', 'instancia_nome')

    fieldsets = (
        ("Conexão", {
            "fields": ("clinic", "instancia_nome", "apikey_instancia", "status_conexao")
        }),
        ("Lembretes 24h", {
            "fields": ("lembretes_ativos", "tipo_envio", "mensagem_confirmacao")
        }),
    )

# -----------------------------
# PROFILE (USUÁRIOS)
# -----------------------------


@admin.register(Profile)
class ProfileAdmin(ModelAdmin):
    list_display = ('user', 'clinic', 'cargo', 'ativo')
    list_filter = ('clinic', 'cargo', 'ativo')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    fields = ('user', 'clinic', 'cargo', 'ativo', 'foto')

# -----------------------------
# PACIENTES
# -----------------------------


@admin.register(Paciente)
class PacienteAdmin(ModelAdmin, ImportExportModelAdmin):
    resource_class = PacienteResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ('nome', 'telefone', 'clinic', 'data_cadastro')
    list_filter = ('clinic', 'data_cadastro')
    search_fields = ('nome', 'telefone', 'email', 'cpf')
    ordering = ('nome',)

# -----------------------------
# CONSULTAS
# -----------------------------


@admin.register(Consulta)
class ConsultaAdmin(ModelAdmin, ImportExportModelAdmin):
    resource_class = ConsultaResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ('paciente', 'data_hora', 'status', 'paga',
                    'clinic', 'lembrete_whatsapp_enviado')
    list_filter = ('clinic', 'status', 'paga',
                   'lembrete_whatsapp_enviado', 'data_hora')
    search_fields = ('paciente__nome',)

    def get_resource_kwargs(self, request, *args, **kwargs):
        kwargs = super().get_resource_kwargs(request, *args, **kwargs)
        if hasattr(request.user, 'profile') and request.user.profile.clinic:
            kwargs.update({'clinic_id': request.user.profile.clinic.id})
        return kwargs

# -----------------------------
# LOGS DE ENVIO
# -----------------------------


@admin.register(LembreteLog)
class LembreteLogAdmin(ModelAdmin):
    list_display = ('consulta', 'tipo', 'status_envio', 'data_envio')
    list_filter = ('status_envio', 'tipo', 'data_envio')
    readonly_fields = ('data_envio', 'mensagem_corpo', 'resposta_paciente')
    search_fields = ('consulta__paciente__nome', 'mensagem_corpo')

# -----------------------------
# FINANCEIRO
# -----------------------------


@admin.register(Financeiro)
class FinanceiroAdmin(ModelAdmin):
    list_display = ('tipo', 'valor', 'data', 'paciente', 'clinic')
    list_filter = ('clinic', 'tipo', 'data')
    search_fields = ('descricao', 'paciente__nome')
    ordering = ('-data',)

# -----------------------------
# CONFIGURAÇÃO VISUAL
# -----------------------------


@admin.register(Configuracao)
class ConfiguracaoAdmin(ModelAdmin):
    list_display = ('clinic', 'nome_clinica', 'nome_profissional')
    search_fields = ('nome_clinica', 'nome_profissional', 'clinic__nome')
