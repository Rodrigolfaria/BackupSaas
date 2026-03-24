from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from home.models import Financeiro, Clinic, Paciente, Consulta

# Função auxiliar para formatar moeda
def format_brl(valor):
    if not valor:
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Removi a herança (BaseWidget) para evitar o erro de import. 
# O Unfold aceita classes puras desde que tenham o método get_context_data.

class FaturamentoSaaSWidget: 
    title = "Faturamento Total SaaS"
    icon = "payments"
    template_name = "unfold/widgets/statistics.html"

    def __init__(self, context=None):
        self.context = context

    def get_context_data(self):
        total = Financeiro.objects.aggregate(Sum('valor'))['valor__sum'] or 0
        return {
            "title": self.title,
            "icon": self.icon,
            "value": format_brl(total),
            "description": "Soma de todos os recebimentos",
        }

class TotalClinicasWidget:
    title = "Clínicas Ativas"
    icon = "health_and_safety"
    template_name = "unfold/widgets/statistics.html"

    def __init__(self, context=None):
        self.context = context

    def get_context_data(self):
        total = Clinic.objects.count()
        return {
            "title": self.title,
            "icon": self.icon,
            "value": total,
            "description": "Total de tenants no SaaS",
        }

class CrescimentoPacientesWidget:
    title = "Novos Pacientes (30 dias)"
    icon = "group_add"
    template_name = "unfold/widgets/statistics.html"

    def __init__(self, context=None):
        self.context = context

    def get_context_data(self):
        periodo = timezone.now() - timedelta(days=30)
        total = Paciente.objects.filter(data_cadastro__gte=periodo).count()
        return {
            "title": self.title,
            "icon": self.icon,
            "value": f"+ {total}",
            "description": "Cadastros no último mês",
        }

class ConsultasHojeWidget:
    title = "Consultas para Hoje"
    icon = "calendar_today"
    template_name = "unfold/widgets/statistics.html"

    def __init__(self, context=None):
        self.context = context

    def get_context_data(self):
        hoje = timezone.now().date()
        total = Consulta.objects.filter(data_hora__date=hoje).count()
        return {
            "title": self.title,
            "icon": self.icon,
            "value": total,
            "description": "Agendamentos para hoje",
        }

class FaturamentoPrevistoWidget:
    title = "Previsão de Receita (Mês)"
    icon = "trending_up"
    template_name = "unfold/widgets/statistics.html"

    def __init__(self, context=None):
        self.context = context

    def get_context_data(self):
        agora = timezone.now()
        total = Consulta.objects.filter(
            data_hora__month=agora.month,
            data_hora__year=agora.year,
            paga=False
        ).count()
        
        return {
            "title": self.title,
            "icon": self.icon,
            "value": f"{total} Pendentes",
            "description": "Consultas não pagas este mês",
        }

class FaturamentoMensalWidget:
    title = "Faturamento Assinaturas"
    icon = "account_balance"
    template_name = "unfold/widgets/statistics.html"

    def __init__(self, context=None):
        self.context = context

    def get_context_data(self):
        planos = getattr(settings, 'PLANOS_CONFIG', {
            'essential': {'preco': 0},
            'professional': {'preco': 0}
        })
        
        essenciais = Clinic.objects.filter(plano='essential').count()
        profissionais = Clinic.objects.filter(plano='professional').count()
        
        total = (essenciais * planos['essential']['preco']) + \
                (profissionais * planos['professional']['preco'])

        return {
            "title": self.title,
            "icon": self.icon,
            "value": format_brl(total),
            "description": f"{essenciais} Essent. | {profissionais} Prof.",
        }