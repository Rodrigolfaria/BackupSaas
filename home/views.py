from .models import Clinic, Profile
from .models import Clinic
from django.utils.html import strip_tags
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import redirect
import mercadopago
from django.http import HttpResponse
from datetime import timedelta
from django.contrib.auth import login
import json
import os
import re
import requests
import traceback
import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from .models import Clinic
from django.http import JsonResponse

from .models import Paciente, ArquivoPaciente


from .models import Consulta, Dentista



from .models import Dentista, Procedimento

# Django Core
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.contrib import messages
# Adicione este import no topo do arquivo
from django.contrib.postgres.aggregates import StringAgg
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.template.loader import get_template, render_to_string
from django.core.management import call_command
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction

# Django DB Models & Functions
from django.db.models import Max, F, Count, Q, Sum, Avg
from django.db.models.functions import TruncDay, TruncMonth, ExtractYear

# Terceiros
from xhtml2pdf import pisa

# Recursos do Projeto (Seus arquivos)
from .models import (
    Paciente, Consulta, Financeiro, Configuracao,
    LembreteLog, ConfiguracaoWhatsApp, HistoricoFidelizacao
)
from .forms import (
    PacienteForm, ConsultaForm, FinanceiroForm,
    ConfiguracaoForm, UsuarioForm
)
from .resources import PacienteResource, ConsultaResource
from .utils import (
    enviar_mensagem_whatsapp,
    google_delete_event,
    google_update_event
)
from .ai_service import AIService

# Configuração de Logs
logger = logging.getLogger(__name__)




# Certifique-se de importar seus modelos

# ---------------------------
# DECORATORS
# ---------------------------


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.profile.cargo != 'admin':
            messages.error(request, "Acesso restrito ao administrador.")
            return redirect('index')
        return view_func(request, *args, **kwargs)
    return wrapper


def cargo_proibido(cargos_bloqueados):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            cargo = request.user.profile.cargo
            if cargo in cargos_bloqueados:
                messages.error(
                    request, "Você não tem permissão para acessar esta página.")
                return redirect('index')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ---------------------------
# PÁGINAS PÚBLICAS
# ---------------------------

def homepage(request):
    return render(request, 'home/homepage.html', {
        'config': None
    })


# ---------------------------
# PÁGINAS PROTEGIDAS
# ---------------------------

@login_required
def index(request):
    return render(request, 'home/index.html')


@login_required
def sobre(request):
    return render(request, 'home/sobre.html')


@login_required
def dashboard(request):
    clinic = request.user.profile.clinic

    # --- CORREÇÃO DE FUSO HORÁRIO ---
    # Pegamos o "hoje" real de Brasília
    agora_local = timezone.localtime(timezone.now())
    today = agora_local.date()
    month = today.month
    # --------------------------------

    consultas_hoje = Consulta.objects.filter(
        clinic=clinic,
        data_hora__date=today
    ).count()

    pacientes_hoje = Paciente.objects.filter(
        clinic=clinic,
        data_cadastro=today
    ).count()

    faturamento_diario = Financeiro.objects.filter(
        clinic=clinic,
        tipo='entrada',
        data=today
    ).aggregate(Sum('valor'))['valor__sum'] or 0

    faturamento_mensal = Financeiro.objects.filter(
        clinic=clinic,
        tipo='entrada',
        data__month=month,
        data__year=today.year  # Adicionado para garantir que não pegue meses de anos passados
    ).aggregate(Sum('valor'))['valor__sum'] or 0

    proximas_consultas = Consulta.objects.filter(
        clinic=clinic,
        data_hora__date=today
    ).order_by('data_hora')

    context = {
        'consultas_hoje': consultas_hoje,
        'pacientes_hoje': pacientes_hoje,
        'faturamento_diario': faturamento_diario,
        'faturamento_mensal': faturamento_mensal,
        'proximas_consultas': proximas_consultas,
    }

    return render(request, 'home/dashboard.html', context)


# ---------------------------
# PACIENTES
# ---------------------------

@login_required
def novo_paciente(request):
    clinic_atual = request.user.profile.clinic

    if request.method == 'POST':
        # Passamos o clinic=clinic_atual para o Form disparar o clean_cpf corretamente
        form = PacienteForm(request.POST, clinic=clinic_atual)

        if form.is_valid():
            try:
                paciente = form.save(commit=False)
                paciente.clinic = clinic_atual
                paciente.save()
                messages.success(request, 'Paciente cadastrado com sucesso!')
                return redirect('lista_pacientes')
            except Exception as e:
                messages.error(request, 'Erro interno ao salvar o paciente.')
        else:
            # Se o CPF for duplicado, o erro já estará dentro do 'form'
            messages.error(
                request, 'Por favor, corrija os erros no formulário.')
    else:
        form = PacienteForm()

    return render(request, 'home/novo_paciente.html', {'form': form})


@login_required
def lista_pacientes(request):
    clinic = request.user.profile.clinic
    busca = request.GET.get('q', '')

    # Começamos filtrando apenas pela clínica logada (Multi-tenant)
    pacientes = Paciente.objects.filter(clinic=clinic).order_by('nome')

    if busca:
        # Filtra por Nome, CPF ou E-mail dentro daquela clínica
        pacientes = pacientes.filter(
            Q(nome__icontains=busca) |
            Q(cpf__icontains=busca) |
            Q(email__icontains=busca)
        )

    # Paginação (mantido em 10 por página conforme seu código)
    paginator = Paginator(pacientes, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'home/lista_pacientes.html', {
        'page_obj': page_obj,
        'busca': busca
    })


@login_required
def editar_paciente(request, id):
    clinic_atual = request.user.profile.clinic
    paciente = get_object_or_404(Paciente, id=id, clinic=clinic_atual)

    if request.method == 'POST':
        # Passamos a clínica e a instância atual para o formulário
        form = PacienteForm(request.POST, instance=paciente,
                            clinic=clinic_atual)

        if form.is_valid():
            try:
                paciente_editado = form.save(commit=False)
                paciente_editado.clinic = clinic_atual
                paciente_editado.save()

                messages.success(request, "Paciente atualizado com sucesso!")
                return redirect('lista_pacientes')
            except Exception as e:
                messages.error(request, "Ocorreu um erro interno ao salvar.")
        else:
            # Se o CPF for duplicado, o erro já virá dentro do form.errors
            messages.error(
                request, "Por favor, corrija os erros no formulário.")
    else:
        # No GET, também passamos a clínica para manter o padrão do __init__
        form = PacienteForm(instance=paciente, clinic=clinic_atual)

    return render(request, 'home/editar_paciente.html', {
        'paciente': paciente,
        'form': form
    })


@require_POST
def verificar_cpf_existente(request):
    cpf = request.POST.get('cpf', '').strip()
    paciente_id = request.POST.get('paciente_id', '')

    if not cpf:
        return JsonResponse({'existe': False})

    existe = Paciente.objects.filter(cpf=cpf).exclude(id=paciente_id).exists()
    return JsonResponse({'existe': existe})


@login_required
def excluir_paciente(request, id):
    clinic = request.user.profile.clinic
    paciente = get_object_or_404(Paciente, id=id, clinic=clinic)

    if request.method == 'POST':
        paciente.delete()
        messages.success(request, 'Paciente excluído com sucesso!')
        return redirect('lista_pacientes')

    return render(request, 'home/excluir_paciente.html', {'paciente': paciente})


@login_required
def detalhes_paciente(request, id):
    clinic = request.user.profile.clinic
    paciente = get_object_or_404(Paciente, id=id, clinic=clinic)

    # Pegamos as consultas
    consultas_queryset = Consulta.objects.filter(
        clinic=clinic,
        paciente=paciente
    ).order_by('-data_hora')

    # CORREÇÃO DE EXIBIÇÃO:
    # Para garantir que o histórico de consultas mostre a hora de Brasília no HTML
    # O Django costuma fazer isso no template com USE_TZ=True,
    # mas converter no queryset é uma boa prática para cálculos se necessário.

    # CALCULA A SOMA TOTAL:
    faturamento_total = consultas_queryset.aggregate(Sum('valor'))[
        'valor__sum'] or 0

    financeiro = Financeiro.objects.filter(
        clinic=clinic,
        paciente=paciente
    ).order_by('-data')

    return render(request, 'home/detalhes_paciente.html', {
        'paciente': paciente,
        'consultas': consultas_queryset,
        'financeiro': financeiro,
        'faturamento_total': faturamento_total
    })




@csrf_exempt # Usado para simplificar o upload via JS, mas garanta que o app seja seguro
def upload_arquivo_paciente(request, paciente_id):
    if request.method == 'POST' and request.FILES.get('arquivo'):
        try:
            paciente = Paciente.objects.get(id=paciente_id)
            novo_arquivo = ArquivoPaciente.objects.create(
                paciente=paciente,
                arquivo=request.FILES.get('arquivo'),
                descricao=request.POST.get('descricao', '') # Opcional
            )
            return JsonResponse({
                'success': True, 
                'url': novo_arquivo.arquivo.url,
                'id': novo_arquivo.id
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Método inválido ou arquivo não enviado.'})


# ---------------------------
# CONSULTAS (CORRIGIDO)
# ---------------------------


@login_required
def agendar(request):
    clinic = request.user.profile.clinic
    tz_sp = ZoneInfo('America/Sao_Paulo')

    if request.method == 'POST':
        form = ConsultaForm(request.POST, clinic=clinic)
        if form.is_valid():
            consulta = form.save(commit=False)
            consulta.clinic = clinic

            # 1. FORÇA O FUSO ANTES DE SALVAR
            if timezone.is_naive(consulta.data_hora):
                consulta.data_hora = timezone.make_aware(
                    consulta.data_hora, tz_sp)
            else:
                consulta.data_hora = consulta.data_hora.astimezone(tz_sp)

            # 2. CALCULA O TÉRMINO (30 MINUTOS DEPOIS)
            # Se você tiver um campo 'data_hora_fim' no banco, salve ele aqui
            # Caso contrário, usaremos esse cálculo apenas para o Google e FullCalendar
            data_fim = consulta.data_hora + timedelta(minutes=30)

            consulta.save()

            try:
                # 3. ENVIANDO A DURAÇÃO PARA O GOOGLE
                # Ajuste a função google_create_event para aceitar o data_fim se necessário
                # Ou garanta que dentro dela você use: end = start + 30min
                event_id = google_create_event(
                    request.user.profile, consulta, data_fim=data_fim)
                if event_id:
                    consulta.google_event_id = event_id
                    consulta.save()
            except Exception as e:
                print(f"Erro ao criar evento no Google: {e}")
                pass

            return redirect('/dashboard/')
    else:
        form = ConsultaForm(clinic=clinic)
        data_inicial = request.GET.get("data")
        if data_inicial:
            # Mantém o 09:00 como padrão se vier do clique no calendário
            form.initial["data_hora"] = f"{data_inicial}T09:00"

    return render(request, 'home/agendar.html', {'form': form})


@login_required
def detalhes_consulta(request, id):
    clinic = request.user.profile.clinic
    consulta = get_object_or_404(Consulta, id=id, clinic=clinic)

    return render(request, 'home/detalhes_consulta.html', {
        'consulta': consulta,
        'paciente': consulta.paciente,
    })


@login_required
def editar_consulta(request, id):
    clinic = request.user.profile.clinic
    consulta = get_object_or_404(Consulta, id=id, clinic=clinic)
    tz_sp = ZoneInfo('America/Sao_Paulo')

    if request.method == 'POST':
        form = ConsultaForm(request.POST, instance=consulta, clinic=clinic)

        if form.is_valid():
            consulta_atualizada = form.save(commit=False)

            # Garante que a edição também preserve o fuso de Brasília
            if timezone.is_naive(consulta_atualizada.data_hora):
                consulta_atualizada.data_hora = timezone.make_aware(
                    consulta_atualizada.data_hora, tz_sp)
            else:
                consulta_atualizada.data_hora = consulta_atualizada.data_hora.astimezone(
                    tz_sp)

            consulta_atualizada.save()

            # Atualiza Google Calendar
            try:
                google_update_event(request.user.profile, consulta_atualizada)
            except (NameError, Exception):
                pass

            # --- LÓGICA FINANCEIRA INTEGRADA ---
            if consulta_atualizada.paga and consulta_atualizada.valor > 0 and consulta_atualizada.status != 'cancelada':
                texto_obs = f" - {consulta_atualizada.observacoes}" if consulta_atualizada.observacoes else ""
                descricao_dinamica = f"Pagamento: {consulta_atualizada.paciente.nome}{texto_obs}"

                # Usa timezone.localtime().date() para o financeiro se a data de pagamento for hoje
                data_financeiro = consulta_atualizada.data_pagamento or timezone.localtime(
                    timezone.now()).date()

                lancamento, created = Financeiro.objects.get_or_create(
                    clinic=clinic,
                    consulta=consulta_atualizada,
                    defaults={
                        'paciente': consulta_atualizada.paciente,
                        'tipo': 'entrada',
                        'valor': consulta_atualizada.valor,
                        'descricao': descricao_dinamica,
                        'data': data_financeiro
                    }
                )

                if not created:
                    lancamento.valor = consulta_atualizada.valor
                    lancamento.data = data_financeiro
                    lancamento.descricao = descricao_dinamica
                    lancamento.save()
            else:
                Financeiro.objects.filter(
                    consulta=consulta_atualizada, clinic=clinic).delete()

            return redirect(f'/consultas/detalhes/{consulta.id}/')
    else:
        form = ConsultaForm(instance=consulta, clinic=clinic)

    return render(request, 'home/editar_consulta.html', {
        'form': form,
        'consulta': consulta,
        'paciente': consulta.paciente,
    })


@login_required
def excluir_consulta(request, id):
    clinic = request.user.profile.clinic
    consulta = get_object_or_404(Consulta, id=id, clinic=clinic)
    paciente_id = consulta.paciente.id

    if request.method == 'POST':
        # 1. FINANCEIRO: Deleta os lançamentos vinculados primeiro
        Financeiro.objects.filter(consulta=consulta, clinic=clinic).delete()

        # 2. GOOGLE CALENDAR: Tenta remover o evento
        # Passamos o profile e a consulta ANTES de deletar a consulta do banco
        if consulta.google_event_id:
            try:
                google_delete_event(request.user.profile, consulta)
            except Exception as e:
                # Logamos o erro mas permitimos que a exclusão no banco continue
                logger.error(f"Erro ao deletar evento Google: {str(e)}")

        # 3. BANCO DE DADOS: Agora sim, removemos a consulta
        consulta.delete()

        messages.success(
            request, "Consulta e registros vinculados excluídos com sucesso.")
        return redirect(f'/pacientes/detalhes/{paciente_id}/')

    return render(request, 'home/excluir_consulta.html', {
        'consulta': consulta,
        'paciente': consulta.paciente,
    })


@login_required
def lista_consultas(request):
    clinic = request.user.profile.clinic

    # --- AJUSTE: Pegar o "hoje" local para filtros e KPIs ---
    agora_local = timezone.localtime(timezone.now())

    busca = request.GET.get('q', '')
    mes_filtro = request.GET.get('mes', str(agora_local.month))
    ano_filtro = request.GET.get('ano', str(agora_local.year))

    queryset = Consulta.objects.filter(clinic=clinic).order_by('data_hora')

    if busca:
        queryset = queryset.filter(
            Q(paciente__nome__icontains=busca) |
            Q(paciente__cpf__icontains=busca) |
            Q(responsavel__nome__icontains=busca) |
            Q(responsavel__cpf__icontains=busca) 
        )

    if mes_filtro:
        queryset = queryset.filter(data_hora__month=mes_filtro)
    if ano_filtro:
        queryset = queryset.filter(data_hora__year=ano_filtro)

    anos_disponiveis = Consulta.objects.filter(clinic=clinic).annotate(
        year=ExtractYear('data_hora')).values_list('year', flat=True).distinct().order_by('-year')

    # KPIs
    filtro_concluidas = Q(status__icontains='confirm') | Q(
        status__icontains='conclu') | Q(status__icontains='finaliza')

    faturamento_total = queryset.filter(filtro_concluidas).aggregate(Sum('valor'))[
        'valor__sum'] or 0
    ticket_medio = queryset.filter(filtro_concluidas).aggregate(
        Avg('valor'))['valor__avg'] or 0

    # Pendentes: Uso do agora_local para precisão
    total_pendentes = queryset.exclude(
        filtro_concluidas | Q(status__icontains='cancela')
    ).filter(
        data_hora__lte=agora_local
    ).count()

    paginator = Paginator(queryset, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'home/partials/consulta_rows.html', {'page_obj': page_obj})

    context = {
        'page_obj': page_obj,
        'busca': busca,
        'mes_filtro': mes_filtro,
        'ano_filtro': ano_filtro,
        'anos_disponiveis': anos_disponiveis,
        'faturamento_total': faturamento_total,
        'ticket_medio': ticket_medio,
        'total_pendentes': total_pendentes,
        'clinic': clinic,
    }
    return render(request, 'home/lista_consultas.html', context)




# --- GESTÃO DE DENTISTAS ---

@login_required
def lista_dentistas(request):
    clinic = request.user.profile.clinic
    # Agora só aparecem os que não foram "excluídos"
    dentistas = Dentista.objects.filter(clinic=clinic, ativo=True) 
    return render(request, 'home/dentistas/lista.html', {'dentistas': dentistas})

@login_required
def adicionar_dentista(request):
    clinic = request.user.profile.clinic
    if request.method == 'POST':
        nome = request.POST.get('nome')
        cro = request.POST.get('cro')
        cor = request.POST.get('cor', '#3788d8')
        
        Dentista.objects.create(
            clinic=clinic,
            nome=nome,
            cro=cro,
            cor_calendario=cor
        )
        return redirect('lista_dentistas')
    return render(request, 'home/dentistas/form.html')

# --- GESTÃO DE PROCEDIMENTOS ---

@login_required
def lista_procedimentos(request):
    clinic = request.user.profile.clinic
    procedimentos = Procedimento.objects.filter(clinic=clinic)
    return render(request, 'home/procedimentos/lista.html', {'procedimentos': procedimentos})

@login_required
def adicionar_procedimento(request):
    clinic = request.user.profile.clinic
    if request.method == 'POST':
        nome = request.POST.get('nome')
        duracao = request.POST.get('duracao', 30)
        valor = request.POST.get('valor', 0).replace(',', '.')
        
        Procedimento.objects.create(
            clinic=clinic,
            nome=nome,
            duracao_estimada=duracao,
            valor_sugerido=valor
        )
        return redirect('lista_procedimentos')
    return render(request, 'home/procedimentos/form.html')



@login_required
def reagendar_drag(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            consulta_id = data.get('id')
            novo_horario_str = data.get('novo_horario')

            clinic = request.user.profile.clinic
            consulta = get_object_or_404(
                Consulta, id=consulta_id, clinic=clinic)
            tz_sp = ZoneInfo('America/Sao_Paulo')

            # 1. TRATAMENTO DE DATA (Correção do erro de atributo)
            novo_horario = parse_datetime(novo_horario_str)
            if not novo_horario:
                return JsonResponse({'success': False, 'error': 'Formato de data inválido.'})

            if timezone.is_naive(novo_horario):
                novo_horario = timezone.make_aware(novo_horario, tz_sp)
            else:
                novo_horario = novo_horario.astimezone(tz_sp)

            # 2. ATUALIZA NO BANCO
            consulta.data_hora = novo_horario
            if consulta.status == 'reagendamento_pendente':
                consulta.status = 'agendada'

            consulta.save()

            # 3. SINCRONIA GOOGLE CALENDAR (Usando seu novo utils.py)
            google_update_event(request.user.profile, consulta)

            # 4. ATUALIZAÇÃO FINANCEIRA
            lancamento = Financeiro.objects.filter(
                consulta=consulta, clinic=clinic).first()

            if lancamento:
                if consulta.paga and consulta.valor > 0 and consulta.status != 'cancelada':
                    nova_data_fin = consulta.data_pagamento or consulta.data_hora.date()
                    lancamento.data = nova_data_fin
                    lancamento.valor = consulta.valor
                    texto_obs = f" - {consulta.observacoes}" if consulta.observacoes else ""
                    lancamento.descricao = f"Pagamento: {consulta.paciente.nome}{texto_obs}"
                    lancamento.save()
                else:
                    lancamento.delete()

            return JsonResponse({'success': True})

        except Exception as e:
            logger.error(f"Erro no reagendar_drag: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False}, status=405)


# ---------------------------
# FINANCEIRO
# ---------------------------


@login_required
@cargo_proibido(['recepcao'])
def financeiro(request):
    clinic = request.user.profile.clinic

    # --- AJUSTE: Pegar o "hoje" local para filtros iniciais ---
    agora_local = timezone.localtime(timezone.now())

    # 1. TRATAMENTO DOS FILTROS (Mês e Ano)
    mes_selecionado = int(request.GET.get('mes', agora_local.month))
    ano_selecionado = int(request.GET.get('ano', agora_local.year))

    # 2. FILTRAGEM DOS REGISTROS
    registros_base = Financeiro.objects.filter(
        clinic=clinic,
        data__month=mes_selecionado,
        data__year=ano_selecionado
    )

    registros = registros_base.order_by('-data')

    # 3. CÁLCULO DOS TOTAIS
    total_entradas = registros_base.filter(
        tipo='entrada'
    ).aggregate(Sum('valor'))['valor__sum'] or 0

    total_saidas = registros_base.filter(
        tipo='saida'
    ).aggregate(Sum('valor'))['valor__sum'] or 0

    saldo = total_entradas - total_saidas

    # 4. AUXILIARES PARA O FILTRO NO HTML
    meses_lista = [
        (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
        (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
        (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro')
    ]
    # Gera lista de anos (ano atual local e os 4 anteriores)
    anos_lista = range(agora_local.year, agora_local.year - 5, -1)

    # 5. LÓGICA DO FORMULÁRIO (POST)
    if request.method == 'POST':
        form = FinanceiroForm(request.POST)
        if form.is_valid():
            lanc = form.save(commit=False)
            lanc.clinic = clinic
            # Se o formulário não vier com data, garantimos que salve a data local de hoje
            if not lanc.data:
                lanc.data = agora_local.date()
            lanc.save()
            messages.success(request, 'Lançamento realizado com sucesso!')
            return redirect('/financeiro/')
    else:
        form = FinanceiroForm()

    return render(request, 'home/financeiro.html', {
        'registros': registros,
        'form': form,
        'total_entradas': total_entradas,
        'total_saidas': total_saidas,
        'saldo': saldo,
        'meses_lista': meses_lista,
        'anos_lista': anos_lista,
        'mes_selecionado': mes_selecionado,
        'ano_selecionado': ano_selecionado,
    })


@login_required
@cargo_proibido(['recepcao'])
def excluir_financeiro(request, id):
    clinic = request.user.profile.clinic
    registro = get_object_or_404(Financeiro, id=id, clinic=clinic)

    if request.method == 'POST':
        registro.delete()
        messages.success(request, 'Registro financeiro excluído.')
        return redirect('/financeiro/')

    return render(request, 'home/excluir_financeiro.html', {'registro': registro})


@login_required
@cargo_proibido(['recepcao'])
def relatorios(request):
    clinic = request.user.profile.clinic

    # --- AJUSTE: Data atual local ---
    agora_local = timezone.localtime(timezone.now())
    ano_atual = agora_local.year
    ano_selecionado = int(request.GET.get('ano', ano_atual))

    # Lista de anos para o select
    lista_anos = range(ano_atual, ano_atual - 5, -1)

    # 2. DADOS ANUAIS (Jan a Dez)
    dados_anuais = Financeiro.objects.filter(
        clinic=clinic,
        data__year=ano_selecionado
    ).annotate(
        mes=TruncMonth('data')
    ).values('mes', 'tipo').annotate(
        total=Sum('valor')
    ).order_by('mes')

    entradas_ano = [0.0] * 12
    saidas_ano = [0.0] * 12
    meses_labels = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai',
                    'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']

    for item in dados_anuais:
        mes_index = item['mes'].month - 1
        if item['tipo'] == 'entrada':
            entradas_ano[mes_index] = float(item['total'])
        else:
            saidas_ano[mes_index] = float(item['total'])

    # 3. FATURAMENTO DIÁRIO (Mês Atual Local)
    dados_diarios = Financeiro.objects.filter(
        clinic=clinic,
        tipo='entrada',
        data__month=agora_local.month,
        data__year=agora_local.year
    ).annotate(
        dia=TruncDay('data')
    ).values('dia').annotate(
        total=Sum('valor')
    ).order_by('dia')

    dias = [item['dia'].strftime('%d/%m') for item in dados_diarios]
    faturamento_dias = [float(item['total']) for item in dados_diarios]

    # 4. TOTAIS GERAIS
    total_entradas = sum(entradas_ano)
    total_saidas = sum(saidas_ano)
    saldo = total_entradas - total_saidas

    context = {
        'lista_anos': lista_anos,
        'ano_selecionado': ano_selecionado,
        'entradas_ano': entradas_ano,
        'saidas_ano': saidas_ano,
        'meses_labels': meses_labels,
        'dias': dias,
        'faturamento_dias': faturamento_dias,
        'total_entradas': total_entradas,
        'total_saidas': total_saidas,
        'saldo': saldo,
    }

    return render(request, 'home/relatorios.html', context)


# ---------------------------
# USUÁRIOS (ADMIN)
# ---------------------------

@login_required
def meu_perfil(request):
    profile = request.user.profile

    if request.method == 'POST':
        # Atualização dos dados básicos do User (se houver lógica para isso)
        # Exemplo: request.user.first_name = request.POST.get('nome')

        # BUSCA A FOTO NO REQUEST
        nova_foto = request.FILES.get('foto')

        # SÓ ATUALIZA SE O USUÁRIO REALMENTE ESCOLHEU UM ARQUIVO
        if nova_foto:
            profile.foto = nova_foto

        # Salva o perfil
        profile.save()

        messages.success(request, "Perfil atualizado!")
        return redirect('meu_perfil')

    return render(request, 'usuarios/meu_perfil.html')


@login_required
@admin_required
def lista_usuarios(request):
    clinic = request.user.profile.clinic
    # Filtramos os usuários que pertencem à clínica do Admin logado
    usuarios = User.objects.filter(
        profile__clinic=clinic).select_related('profile')
    return render(request, 'usuarios/lista.html', {'usuarios': usuarios})


@login_required
@admin_required
def criar_usuario(request):
    clinic = request.user.profile.clinic

    if request.method == 'POST':
        form = UsuarioForm(request.POST)
        if form.is_valid():
            user = form.save()
            cargo = form.cleaned_data['cargo']
            ativo = form.cleaned_data.get('ativo', True)

            # Vincula à clínica do Admin logado
            user.profile.clinic = clinic
            user.profile.cargo = cargo
            user.profile.ativo = ativo
            user.profile.save()

            # Garante consistência com o is_active do Django
            user.is_active = ativo
            user.save()

            messages.success(
                request, f"Usuário {user.username} criado com sucesso.")
            return redirect('lista_usuarios')
    else:
        form = UsuarioForm()

    return render(request, 'home/criar_usuario.html', {'form': form})


@login_required
@admin_required
def editar_usuario(request, user_id):
    # SEGURANÇA: Só permite buscar o usuário se ele pertencer à mesma clínica do Admin
    clinic_admin = request.user.profile.clinic
    user = get_object_or_404(User, id=user_id, profile__clinic=clinic_admin)

    if request.method == "POST":
        cargo_form = request.POST.get('cargo')
        # Captura o checkbox (True se marcado, False se não estiver no POST)
        ativo_form = 'ativo' in request.POST

        # Salva no perfil
        perfil = user.profile
        perfil.cargo = cargo_form
        perfil.ativo = ativo_form
        perfil.save()

        # Sincroniza com a conta do Django
        user.is_active = ativo_form
        user.save()

        messages.success(request, f"Usuário {user.username} atualizado.")
        return redirect('lista_usuarios')

    return render(request, 'usuarios/editar.html', {'usuario': user})

# ---------------------------
# CONFIGURAÇÕES (ADMIN)
# ---------------------------


@login_required
@admin_required
def configuracoes(request):
    clinic = request.user.profile.clinic
    # Ajustado para garantir que use a clinic do usuário logado como chave
    config, created = Configuracao.objects.get_or_create(clinic=clinic)

    if request.method == 'POST':
        form = ConfiguracaoForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Configurações atualizadas com sucesso.")
            return redirect('configuracoes')
    else:
        form = ConfiguracaoForm(instance=config)

    return render(request, 'home/configuracoes.html', {
        'form': form,
        'config': config
    })


@login_required
def consultas_hoje(request):
    clinic = request.user.profile.clinic

    # 1. Obtém o momento atual no fuso de Brasília
    agora_local = timezone.localtime(timezone.now())
    hoje = agora_local.date()

    # 2. Filtramos as consultas por range local de 24h
    start_of_day = agora_local.replace(
        hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    consultas = Consulta.objects.filter(
        clinic=clinic,
        data_hora__range=(start_of_day, end_of_day)
    ).order_by('data_hora')

    return render(request, 'home/consultas_hoje.html', {
        'consultas': consultas,
        'hoje': hoje
    })


@login_required
def recibo_consulta(request, id):
    clinic = request.user.profile.clinic
    # Segurança: get_object_or_404 com clinic garante que um usuário não veja recibo de outro
    consulta = get_object_or_404(Consulta, id=id, clinic=clinic)
    config = Configuracao.objects.filter(clinic=clinic).first()

    context = {
        'consulta': consulta,
        'config': config,
        'clinic': clinic,
        'user': request.user,
    }
    return render(request, 'home/recibo_consulta.html', context)


@login_required
def baixar_pdf_recibo(request, id):
    clinic = request.user.profile.clinic
    consulta = get_object_or_404(Consulta, id=id, clinic=clinic)
    config = Configuracao.objects.filter(clinic=clinic).first()

    context = {
        'consulta': consulta,
        'config': config,
        'clinic': clinic,
        'user': request.user,
    }

    def link_callback(uri, rel):
        if uri.startswith(settings.MEDIA_URL):
            return os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
        if uri.startswith(settings.STATIC_URL):
            return os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
        return uri

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="recibo_{consulta.id}.pdf"'

    template_path = 'home/recibo_consulta.html'
    template = get_template(template_path)
    html = template.render(context)

    pisa_status = pisa.CreatePDF(
        html, dest=response, link_callback=link_callback)

    if pisa_status.err:
        return HttpResponse('Erro ao gerar PDF', status=500)

    return response


@login_required
def consultas_json(request):
    # 🔥 SEGURANÇA: Antes estava .all(), agora filtra pela clínica do usuário logado
    clinic = request.user.profile.clinic
    consultas = Consulta.objects.filter(clinic=clinic)

    eventos = []
    for consulta in consultas:
        # 🔥 HORA: Convertendo para local antes de enviar o ISO para o calendário
        data_local = timezone.localtime(consulta.data_hora)

        eventos.append({
            "id": consulta.id,
            "title": consulta.paciente.nome,
            "start": data_local.isoformat(),
            "end": (data_local + timedelta(hours=1)).isoformat(),
            "url": reverse("detalhes_consulta", args=[consulta.id])
        })

    return JsonResponse(eventos, safe=False)


@login_required
@login_required
def agenda_events(request):
    clinic = request.user.profile.clinic
    dentista_id = request.GET.get('dentista_id')
    
    # Debug: Veja no seu terminal se o ID está chegando certo
    print(f"DEBUG: Filtrando para o dentista ID: {dentista_id}")

    consultas = Consulta.objects.filter(clinic=clinic).select_related('paciente', 'dentista')

    # Ajuste na lógica de filtro para ser mais rigorosa
    if dentista_id and dentista_id not in ['todos', '', 'undefined', 'null']:
        try:
            consultas = consultas.filter(dentista_id=int(dentista_id))
        except ValueError:
            pass # Caso o ID não seja um número válido

    tz_br = ZoneInfo('America/Sao_Paulo')
    eventos = []

    for consulta in consultas:
        data_local = consulta.data_hora.astimezone(tz_br)
        data_fim_local = data_local + timedelta(minutes=30)
        status = (consulta.status or "").lower()

        # Definição de Cores (Sua lógica original mantida)
        if status in ['confirmada', 'confirmado']:
            cor_fundo, cor_texto, cor_borda = '#dcfce7', '#15803d', '#15803d'
        elif status in ['finalizada', 'finalizado']:
            cor_fundo, cor_texto, cor_borda = "#ffffff", '#064e3b', '#059669'
        elif status in ['cancelada', 'cancelado']:
            cor_fundo, cor_texto, cor_borda = '#fee2e2', '#b91c1c', '#b91c1c'
        elif status == 'reagendamento_pendente':
            cor_fundo, cor_texto, cor_borda = '#ffedd5', '#c2410c', '#c2410c'
        else:
            cor_fundo, cor_texto, cor_borda = '#fef9c3', '#a16207', '#ca8a04'

        eventos.append({
            "id": consulta.id,
            "title": f"{consulta.paciente.nome}",
            "start": data_local.isoformat(),
            "end": data_fim_local.isoformat(),
            "url": f"/consultas/detalhes/{consulta.id}/",
            "backgroundColor": cor_fundo,
            "textColor": cor_texto,
            "borderColor": cor_borda,
            "extendedProps": {
                "status": status,
                "paciente": consulta.paciente.nome,
                "dentista": consulta.dentista.nome if consulta.dentista else "Geral"
            }
        })

    return JsonResponse(eventos, safe=False)


@login_required
def agenda(request):
    clinic = request.user.profile.clinic
    # IMPORTANTE: Filtrar por ativo=True aqui também!
    dentistas = Dentista.objects.filter(clinic=clinic, ativo=True).order_by('nome')
    
    return render(request, 'home/agenda.html', {
        'dentistas_da_clinica': dentistas,
        'clinic': clinic
    })

# ---------------------------
# GOOGLE CALENDAR - OAUTH
# ---------------------------


GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI = settings.GOOGLE_REDIRECT_URI


@login_required
def google_auth(request):
    # Adicionado state para segurança contra ataques CSRF (opcional, mas recomendado)
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        "&scope=https://www.googleapis.com/auth/calendar"
        "&access_type=offline"
        "&prompt=consent"
    )
    return redirect(auth_url)


@login_required
def google_callback(request):
    code = request.GET.get("code")

    if not code:
        messages.error(
            request, "Conexão cancelada ou erro ao conectar com o Google.")
        return redirect("agenda")

    token_url = "https://oauth2.googleapis.com/token"

    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    try:
        response = requests.post(token_url, data=data)
        token_data = response.json()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")

        if not access_token:
            messages.error(
                request, "Erro ao obter token do Google. Verifique suas credenciais.")
            return redirect("agenda")

        profile = request.user.profile
        profile.google_access_token = access_token

        # 🔥 SEGURANÇA: Só atualizamos o refresh_token se o Google enviar um novo
        # (O Google só envia o refresh_token na primeira vez ou quando o prompt é 'consent')
        if refresh_token:
            profile.google_refresh_token = refresh_token

        # 🔥 HORA: Calculando a expiração baseada no fuso atual
        profile.google_token_expiry = timezone.now() + timedelta(seconds=expires_in)
        profile.save()

        messages.success(request, "Google Calendar conectado com sucesso!")

    except Exception as e:
        messages.error(request, f"Erro inesperado na autenticação: {e}")

    return redirect("agenda")

# ---------------------------
# GOOGLE CALENDAR - FUNÇÕES DE SINCRONIZAÇÃO
# ---------------------------


def google_refresh_token(profile):
    """Renova o access_token quando expirar."""
    if not profile.google_refresh_token:
        return None

    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": profile.google_refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        response = requests.post(url, data=data).json()
        new_token = response.get("access_token")
        expires_in = response.get("expires_in")

        if new_token:
            profile.google_access_token = new_token
            # Mantemos a expiração baseada no tempo de servidor (UTC)
            profile.google_token_expiry = timezone.now() + timedelta(seconds=expires_in)
            profile.save()
            return new_token
    except Exception as e:
        print(f"Erro ao renovar token Google: {e}")

    return None


def google_get_token(profile):
    """Retorna um access_token válido, renovando se necessário."""
    if not profile.google_access_token:
        return None

    # Verifica se o token expirou ou está prestes a expirar (margem de 1 minuto)
    agora = timezone.now()
    if profile.google_token_expiry and profile.google_token_expiry < (agora + timedelta(minutes=1)):
        return google_refresh_token(profile)

    return profile.google_access_token


def google_create_event(profile, consulta, data_fim=None): # <--- Adicionado data_fim=None
    """Cria evento no Google Calendar com fuso horário correto."""
    token = google_get_token(profile)
    if not token:
        return None

    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

    # HORA: Convertemos para o horário de Brasília
    data_inicio = timezone.localtime(consulta.data_hora)
    
    # Se a view enviou data_fim, usamos. Se não, calculamos o padrão de 1h
    if data_fim:
        # Garante que a data vinda da view também esteja no fuso local
        data_fim_final = timezone.localtime(data_fim)
    else:
        data_fim_final = data_inicio + timedelta(hours=1)

    data = {
        "summary": f"Consulta - {consulta.paciente.nome}",
        "description": f"Responsável: {consulta.responsavel or 'Não informado'}\nObs: {consulta.observacoes or ''}",
        "start": {"dateTime": data_inicio.isoformat()},
        "end": {"dateTime": data_fim_final.isoformat()}, # <--- Usando a variável tratada
    }

    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.post(url, json=data, headers=headers)
        # É mais seguro verificar o status antes de dar .json()
        if response.status_code in [200, 201]:
            return response.json().get("id")
        return None
    except Exception as e:
        print(f"Erro ao criar evento Google: {e}")
        return None


def google_update_event(profile, consulta):
    """Atualiza evento existente no Google Calendar."""
    if not consulta.google_event_id:
        return google_create_event(profile, consulta)

    token = google_get_token(profile)
    if not token:
        return None

    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{consulta.google_event_id}"

    # 🔥 HORA: Mesma lógica de conversão local
    data_inicio = timezone.localtime(consulta.data_hora)
    data_fim = data_inicio + timedelta(hours=1)

    data = {
        "summary": f"Consulta - {consulta.paciente.nome}",
        "description": f"Responsável: {consulta.responsavel or 'Não informado'}\nObs: {consulta.observacoes or ''}",
        "start": {"dateTime": data_inicio.isoformat()},
        "end": {"dateTime": data_fim.isoformat()},
    }

    headers = {"Authorization": f"Bearer {token}"}

    try:
        requests.put(url, json=data, headers=headers)
    except Exception as e:
        print(f"Erro ao atualizar evento Google: {e}")


def google_delete_event(profile, consulta):
    """Remove evento do Google Calendar."""
    if not consulta.google_event_id:
        return

    token = google_get_token(profile)
    if not token:
        return

    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{consulta.google_event_id}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        requests.delete(url, headers=headers)
    except Exception as e:
        print(f"Erro ao deletar evento Google: {e}")

# ---------------------------
# Exportar & Importar
# ---------------------------


@login_required
def exportar_pacientes(request):
    clinic = request.user.profile.clinic
    # Garante que apenas os pacientes da clínica logada sejam exportados
    queryset = Paciente.objects.filter(clinic=clinic)

    paciente_resource = PacienteResource()
    dataset = paciente_resource.export(queryset)

    response = HttpResponse(
        dataset.xlsx,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    # Nome do arquivo personalizado com o nome da clínica
    response[
        'Content-Disposition'] = f'attachment; filename="pacientes_{clinic.nome.replace(" ", "_")}.xlsx"'
    return response


@login_required
def importar_pacientes(request):
    clinic = request.user.profile.clinic

    if request.method == 'POST':
        novo_arquivo = request.FILES.get('arquivo')
        if not novo_arquivo:
            messages.error(
                request, "Selecione um arquivo .xlsx para continuar.")
            return redirect('lista_pacientes')

        try:
            import tablib
            from .resources import PacienteResource

            # 1. Carrega os dados brutos do Excel
            raw_data = novo_arquivo.read()
            dataset_original = tablib.Dataset().load(raw_data, format='xlsx')

            # 2. RECONSTRUÇÃO (Segurança Multi-tenant)
            # Forçamos a coluna 'clinic' para garantir que NENHUM paciente
            # caia em outra conta, independente do que venha no Excel.
            headers = list(dataset_original.headers)
            if 'clinic' not in headers:
                headers.append('clinic')

            dataset_final = tablib.Dataset(headers=headers)

            for row in dataset_original:
                # Criamos um dicionário da linha para manipular com segurança
                row_dict = dict(zip(dataset_original.headers, row))
                # Injetamos o ID da clínica atual
                row_dict['clinic'] = clinic.id

                # Adicionamos ao dataset final mantendo a ordem dos headers
                dataset_final.append([row_dict.get(h) for h in headers])

            # 3. Processamento com o Resource
            resource = PacienteResource()
            # dry_run=False efetiva a gravação no banco
            result = resource.import_data(
                dataset_final, dry_run=False, raise_errors=False)

            if result.has_errors():
                # Pega o primeiro erro para dar um feedback claro ao usuário
                for row_error in result.row_errors():
                    linha = row_error[0] + 1
                    erros = [str(e.error) for e in row_error[1]]
                    messages.error(
                        request, f"Erro na Linha {linha}: {', '.join(erros)}")
                    break  # Exibe apenas o primeiro para não poluir a tela
            else:
                messages.success(
                    request, f"Sucesso! {result.total_rows} pacientes processados para a clínica {clinic.nome}.")

        except Exception as e:
            messages.error(
                request, f"Falha ao processar arquivo: Verifique se o formato está correto. (Erro: {str(e)})")

        return redirect('lista_pacientes')


@login_required
def baixar_exemplo_pacientes(request):
    """
    Gera um modelo XLSX completo para importação de pacientes.
    """
    import tablib

    headers = [
        'nome',          # Nome exato do campo no Model/Resource
        'telefone',
        'data_nascimento',
        'cpf',
        'endereco',
        'numero',
        'bairro',
        'cidade',
        'uf'
    ]

    dataset = tablib.Dataset(headers=headers, title="Modelo Importação")

    # Linha de exemplo com dados fictícios
    # 🔥 HORA: Usamos o localtime para a data de exemplo se necessário
    dataset.append([
        'João da Silva Exemplo',
        '11999999999',
        '1990-05-15',
        '12345678900',
        'Rua de Exemplo',
        '100',
        'Centro',
        'São Paulo',
        'SP'
    ])

    response = HttpResponse(
        dataset.xlsx,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="modelo_importacao_odonto.xlsx"'

    return response
# ---------------------------
# CONSULTAS - GESTÃO E DADOS
# ---------------------------


@login_required
def consultas_em_aberto(request):
    """
    Lista consultas da clínica que já passaram do horário ou são de agora,
    mas ainda constam como 'agendada' e não foram pagas.
    """
    clinic = request.user.profile.clinic

    # 🔥 HORA: Usamos o momento atual local para comparar com o banco
    agora_local = timezone.localtime(timezone.now())

    consultas = Consulta.objects.filter(
        clinic=clinic,
        status='agendada',
        paga=False,
        # Compara com o horário de Brasília (Django converte internamente para UTC)
        data_hora__lte=agora_local
    ).order_by('data_hora')

    return render(request, 'home/consultas_em_aberto.html', {
        'consultas': consultas,
        'agora': agora_local
    })


@login_required
def exportar_consultas(request):
    """Gera Excel de consultas filtradas pela clínica do usuário logado"""
    clinic = request.user.profile.clinic

    # SEGURANÇA: Filtro obrigatório por clínica
    queryset = Consulta.objects.filter(clinic=clinic)

    resource = ConsultaResource()
    dataset = resource.export(queryset)

    response = HttpResponse(
        dataset.xlsx,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    # Limpeza do nome do arquivo
    filename = f"consultas_{clinic.nome.replace(' ', '_').lower()}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response


@login_required
def importar_consultas(request):
    """
    Importa consultas garantindo o vínculo com a clínica do usuário logado.
    """
    clinic = request.user.profile.clinic

    if request.method == 'POST':
        novo_arquivo = request.FILES.get('arquivo')
        if not novo_arquivo:
            messages.error(request, "Por favor, selecione um arquivo .xlsx")
            return redirect('lista_consultas')

        try:
            from .resources import ConsultaResource
            import tablib

            data = novo_arquivo.read()
            dataset = tablib.Dataset().load(data, format='xlsx')

            # 🔥 AJUSTE PRINCIPAL: Instanciando o Resource com o clinic_id
            # Isso resolve o "Erro de Segurança" que você recebeu
            resource = ConsultaResource(clinic_id=clinic.id)

            # Reconstruímos o dataset para garantir integridade dos headers
            headers = list(dataset.headers)
            novo_dataset = tablib.Dataset(headers=headers)

            for row in dataset.dict:
                novo_dataset.append([row.get(h) for h in headers])

            # O Resource agora sabe que deve usar clinic.id em cada linha salva
            result = resource.import_data(novo_dataset, dry_run=False)

            if result.has_errors():
                # Feedback de erro mais detalhado para o desenvolvedor (você)
                for row_idx, row_errors in result.row_errors():
                    for error in row_errors:
                        messages.error(
                            request, f"Erro na linha {row_idx + 1}: {error.error}")
                        break
                    break
            else:
                messages.success(
                    request, f"Sucesso! {result.total_rows} consultas processadas para {clinic.nome}.")

        except Exception as e:
            # Captura erros estruturais ou de permissão
            messages.error(request, f"Erro estrutural no arquivo: {str(e)}")

    return redirect('lista_consultas')


@login_required
def baixar_modelo_consultas(request):
    import tablib
    from django.http import HttpResponse
    from django.utils import timezone

    # Headers sincronizados com o column_name do ConsultaResource
    headers = [
        'DATA',
        'NOME DO PACIENTE',
        'CPF',
        'NOME DO RESPONSAVEL',
        'VALOR',
        'FORMA DE PAGAMENTO',
        'OBSERVACOES'
    ]

    dataset = tablib.Dataset(headers=headers, title="Modelo Importação")

    # Gerando uma data de exemplo no fuso horário local
    agora_exemplo = timezone.localtime(
        timezone.now()).strftime('%d/%m/%Y %H:%M')

    # Exemplo 1: Paciente Adulto (sem responsável separado)
    dataset.append([
        agora_exemplo,
        'João da Silva',
        '123.456.789-00',
        '',  # Deixe vazio se ele for o próprio responsável
        'R$ 200,00',
        'Pix',
        'Consulta de rotina'
    ])

    # Exemplo 2: Paciente Menor (com responsável vinculado)
    dataset.append([
        agora_exemplo,
        'Enzo Silva (Criança)',
        '987.654.321-99',
        # O seu widget buscará/criará a Maria como paciente
        'Maria Silva (Mãe)',
        'R$ 150,00',
        'Cartão de Crédito',
        'Manutenção preventiva'
    ])

    # Gerando o arquivo Excel (XLSX)
    response = HttpResponse(
        dataset.xlsx,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    # Nome do arquivo que o usuário baixará
    response['Content-Disposition'] = 'attachment; filename="modelo_importacao_odontoclinics.xlsx"'

    return response


def manual_operacao(request):
    # Esta view apenas renderiza o template do manual
    # Ajuste o caminho se seu template estiver em outra pasta
    return render(request, 'home/manual.html')

# ---------------------------
# WEBHOOK
# ---------------------------


@csrf_exempt
def webhook_whatsapp(request):
    """
    Identifica o paciente por Message ID ou JID, atualiza a consulta 
    e responde usando mensagens personalizadas do banco de dados.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)

        # Extração de dados da Evolution API
        evento = data.get('event')
        instancia_nome = data.get('instance')
        payload = data.get('data', {})

        # --- AJUSTE AQUI: Extração segura do remote_jid ---
        # Verifica se o payload é lista ou dicionário e busca o JID
        temp_data = payload[0] if isinstance(payload, list) else payload
        # Tenta buscar em 'key' (mensagens) ou direto no payload (contatos)
        remote_jid = temp_data.get('key', {}).get(
            'remoteJid') or temp_data.get('remoteJid', '')

        # Agora o 'if' funciona porque a variável remote_jid já existe
        if any(suffix in remote_jid for suffix in ['@g.us', '@status', '@broadcast']):
            print(
                f"🚀 OdontoClinics: Ignorando evento de grupo/status: {remote_jid}")
            return JsonResponse({'status': 'ignored_group_or_status'}, status=200)

        if evento != 'messages.upsert':
            return JsonResponse({'status': 'event_ignored'}, status=200)

        # ... restante do código

        key = payload.get('key', {})
        # Evita responder a si mesmo
        if key.get('fromMe', False):
            return JsonResponse({'status': 'ignored_from_me'}, status=200)

        # --- SEGURANÇA MULTI-TENANT ---
        config = ConfiguracaoWhatsApp.objects.filter(
            instancia_nome=instancia_nome).first()

        if not config:
            print(f"⚠️ Instância {instancia_nome} não configurada no sistema.")
            return JsonResponse({'error': 'Instance not found'}, status=404)

        remote_jid = key.get('remoteJid', '')
        message_content = payload.get('message', {})

        # Captura o texto da resposta
        msg_texto_original = (
            message_content.get('conversation') or
            message_content.get('extendedTextMessage', {}).get('text') or
            message_content.get('buttonsResponseMessage', {}).get(
                'selectedButtonId') or ""
        )
        texto_limpo = msg_texto_original.lower().strip()

        if not remote_jid or not texto_limpo:
            return JsonResponse({'status': 'no_data_to_process'}, status=200)

        # Captura do ID da mensagem citada (Stanza ID)
        context_info = (
            message_content.get('extendedTextMessage', {}).get('contextInfo') or
            message_content.get('buttonsResponseMessage', {}).get('contextInfo') or
            message_content.get('contextInfo', {})
        )
        quoted_id = context_info.get('stanzaId')

        print(
            f"📩 Webhook [{instancia_nome}] Quoted: {quoted_id}: '{texto_limpo}'")

        paciente = None
        consulta = None

        # --- 2. IDENTIFICAÇÃO DO PACIENTE (ESTRATÉGIA MULTI-CAMADA) ---

        # CAMADA 1: Por Message ID (A mais precisa para evitar o erro do print)
        if quoted_id:
            ultimo_log = LembreteLog.objects.filter(
                message_id=quoted_id,
                status_envio='enviado'
            ).select_related('consulta__paciente', 'consulta__clinic').first()

            if ultimo_log and ultimo_log.consulta.clinic == config.clinic:
                paciente = ultimo_log.consulta.paciente
                consulta = ultimo_log.consulta
                print(f"✅ Identificado por Message ID: {paciente.nome}")

        # CAMADA 2: Por JID direto na clínica correta
        if not paciente:
            paciente = Paciente.objects.filter(
                clinic=config.clinic, whatsapp_jid=remote_jid).first()
            if paciente:
                print(f"ℹ️ Identificado por JID: {paciente.nome}")

        # CAMADA 3: Busca por JID Alternativo
        remote_jid_alt = key.get('remoteJidAlt')
        if not paciente and remote_jid_alt:
            paciente = Paciente.objects.filter(
                clinic=config.clinic, whatsapp_jid=remote_jid_alt).first()
            if paciente:
                paciente.whatsapp_jid = remote_jid
                paciente.save(update_fields=['whatsapp_jid'])

        # CAMADA 4: Fallback Temporal (Últimos 60 min)
        if not paciente:
            agora = timezone.now()
            ultimo_log_temp = LembreteLog.objects.filter(
                consulta__clinic=config.clinic,
                status_envio='enviado',
                data_envio__gte=agora - timedelta(minutes=60)
            ).select_related('consulta__paciente').order_by('-data_envio').first()

            if ultimo_log_temp:
                paciente = ultimo_log_temp.consulta.paciente
                paciente.whatsapp_jid = remote_jid
                paciente.save(update_fields=['whatsapp_jid'])

        if not paciente:
            return JsonResponse({'status': 'patient_not_found'}, status=200)

        # --- 3. BUSCA CONSULTA ATIVA (Caso não tenha sido achada no quoted_id) ---
        if not consulta:
            agora = timezone.now()

            # Prioridade: 'agendada' + 'lembrete enviado'
            consulta = Consulta.objects.filter(
                clinic=config.clinic,
                paciente=paciente,
                status='agendada',
                data_hora__gte=agora - timedelta(hours=2),
                lembrete_whatsapp_enviado=True
            ).order_by('data_hora').first()

            # Fallback: Qualquer agendada futura do paciente
            if not consulta:
                consulta = Consulta.objects.filter(
                    clinic=config.clinic,
                    paciente=paciente,
                    status='agendada',
                    data_hora__gte=agora
                ).order_by('data_hora').first()

        if not consulta:
            return JsonResponse({'status': 'no_active_appointment'}, status=200)

        # --- 4. PROCESSAMENTO DA RESPOSTA ---
        confirmacao = ['sim', 'confirmar', 'confirmo', 'confirmado',
                       'ok', 'pode', 'vou', 'estarei', 'com certeza']
        negacao = ['não', 'nao', 'cancelar', 'reagendar',
                   'mudar', 'desmarcar', 'remarcar', 'posso', 'consigo']
        agradecimentos = ['obrigado', 'obrigada', 'valeu', 'vlw',
                          'show', 'blz', 'muito obrigado', 'muito obrigada', 'obgd']
        saudacoes = ['bom dia', 'boa tarde',
                     'boa noite', 'olá', 'ola', 'oie', 'tudo bem']

        nome_clinica = config.clinic.nome if config.clinic else "nossa clínica"
        data_hora_formatada = timezone.localtime(
            consulta.data_hora).strftime('%d/%m às %H:%M')
        primeiro_nome = paciente.nome.split()[0]

        if any(word in texto_limpo for word in confirmacao):
            consulta.status = 'confirmada'
            consulta.save()
            msg_retorno = config.mensagem_sucesso_confirmacao.format(
                paciente=primeiro_nome,
                data_hora=data_hora_formatada,
                clinica=nome_clinica
            )

        elif any(word in texto_limpo for word in negacao):
            consulta.status = 'reagendamento_pendente'
            consulta.save()
            msg_retorno = config.mensagem_solicitacao_reagendamento.format(
                paciente=primeiro_nome,
                clinica=nome_clinica
            )

        else:
            # --- RESPOSTA DE CORTESIA (SOMENTE SE O BOT INICIOU O CONTATO) ---
            # A trava 'consulta.lembrete_whatsapp_enviado' garante que o bot só fale
            # se ele tiver disparado um lembrete para esta consulta específica.

            if any(word in texto_limpo for word in agradecimentos) and consulta.lembrete_whatsapp_enviado:
                msg_retorno = (f"Nós que agradecemos a sua confiança, *{primeiro_nome}*! "
                               f"Cuidar do seu sorriso é uma honra para toda a equipe da *{nome_clinica}*. "
                               f"Nos vemos em breve! ✨")
                print(f"😊 Paciente agradeceu ao lembrete enviado.")

            elif any(word in texto_limpo for word in saudacoes) and consulta.lembrete_whatsapp_enviado:
                msg_retorno = (f"Olá, *{primeiro_nome}*! Tudo bem? 😊 "
                               f"Estou aqui para te ajudar com seu agendamento de {data_hora_formatada} na *{nome_clinica}*. "
                               f"Você gostaria de confirmar (SIM) ou reagendar (NÃO)?")
                print(f"👋 Paciente saudou o bot após o lembrete.")

            # Se a consulta já estiver resolvida OU se o bot NÃO iniciou a conversa, silenciamos.
            elif consulta.status in ['confirmada', 'finalizada', 'cancelada'] or not consulta.lembrete_whatsapp_enviado:
                print(
                    f"🙊 Mensagem ignorada: consulta resolvida ou bot não iniciou o contato.")
                return JsonResponse({'status': 'ignored_to_prevent_intrusion'}, status=200)

            else:
                # Caso contrário (paciente mandou algo que não entendi em resposta ao lembrete)
                msg_retorno = (f"Olá, *{primeiro_nome}*! Não entendi sua resposta. "
                               f"Por favor, responda *SIM* para confirmar seu horário de {data_hora_formatada} "
                               f"ou *NÃO* para reagendar.")

        # --- 1.1 TRAVA DE SEGURANÇA (EVITA REPETIÇÃO) ---
        message_id_recebida = payload.get('key', {}).get('id')

        if message_id_recebida and LembreteLog.objects.filter(message_id=message_id_recebida, status_envio='recebido').exists():
            print(
                f"🛑 Mensagem {message_id_recebida} já processada. Ignorando para evitar duplicidade.")
            return JsonResponse({'status': 'already_processed'}, status=200)

        # ... (seu código de identificação de paciente e consulta continua aqui) ...

        # --- 5. LOG E DISPARO ---

        # Agora salvamos o log com o ID que capturamos lá no início
        LembreteLog.objects.create(
            consulta=consulta,
            status_envio='recebido',
            resposta_paciente=msg_texto_original,
            tipo="Resposta Paciente",
            message_id=message_id_recebida  # <-- ADEUS AO NULL!
        )

        if paciente.whatsapp_jid != remote_jid:
            paciente.whatsapp_jid = remote_jid
            paciente.save(update_fields=['whatsapp_jid'])

        # Dispara a resposta usando o utils.py
        sucesso, res_envio = enviar_mensagem_whatsapp(
            config=config,
            jid_ou_numero=remote_jid,
            texto=msg_retorno,
            retornar_json=True
        )

        # OPCIONAL: Log da resposta que o próprio BOT acabou de enviar
        if sucesso and res_envio:
            try:
                data_res = res_envio[0] if isinstance(
                    res_envio, list) else res_envio
                if 'data' in data_res:
                    data_res = data_res['data']
                if isinstance(data_res, list):
                    data_res = data_res[0]

                msg_id_bot = data_res.get('key', {}).get(
                    'id') or data_res.get('messageId')

                LembreteLog.objects.create(
                    consulta=consulta,
                    status_envio='enviado',
                    mensagem_corpo=msg_retorno,
                    tipo="Resposta Automática Bot",
                    message_id=msg_id_bot
                )
            except Exception as e:
                print(f"⚠️ Não foi possível logar a resposta do bot: {e}")

        return JsonResponse({'status': 'processed', 'delivered': sucesso}, status=200)

    except Exception as e:
        print(f"🚨 Erro crítico Webhook: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'error': 'Internal Server Error'}, status=200)

# ----------------------------------------------------------------
# 2. FUNÇÃO AUXILIAR DE RESPOSTA
# ----------------------------------------------------------------


def responder_whatsapp(config, jid_ou_numero, texto, jid_alternativo=None):
    """
    Envia mensagem via Evolution API com tratamento de erro 400 (LID).
    Garante a entrega usando JID direto ou fallback para número formatado.
    """
    base_url = os.getenv("EVOLUTION_API_URL_BASE")
    if not base_url:
        print("🚨 Erro: EVOLUTION_API_URL_BASE não configurada no .env")
        return False

    url = f"{base_url}/message/sendText/{config.instancia_nome}"
    api_key = config.apikey_instancia or os.getenv("EVOLUTION_API_KEY")
    headers = {"apikey": api_key, "Content-Type": "application/json"}

    def disparar(dest):
        if not dest:
            return None

        # --- NORMALIZAÇÃO DO DESTINATÁRIO ---
        dest = str(dest).strip()

        # Se for um LID (Linked Identity), enviamos como está
        if "@lid" in dest:
            dest_final = dest
        # Se já for um JID padrão, mantemos
        elif "@s.whatsapp.net" in dest:
            dest_final = dest
        else:
            # Limpeza total de caracteres não numéricos para fallback por telefone
            digitos = re.sub(r'\D', '', dest.split('@')[0])

            # Validação básica de número brasileiro
            if digitos:
                if len(digitos) <= 11 and not digitos.startswith("55"):
                    digitos = f"55{digitos}"
                dest_final = f"{digitos}@s.whatsapp.net"
            else:
                return None

        payload = {
            "number": dest_final,
            "text": texto,
            "delay": 1200,  # Delay sutil para humanizar o envio
            "linkPreview": True
        }

        try:
            print(f"📡 Enviando WhatsApp para {dest_final}...")
            response = requests.post(
                url, json=payload, headers=headers, timeout=15)
            # Log de status para monitoramento da instância
            if response.status_code not in [200, 201]:
                print(
                    f"⚠️ Resposta API ({dest_final}): {response.status_code} - {response.text}")
            return response
        except requests.exceptions.RequestException as e:
            print(f"🚨 Erro de conexão com Evolution API: {e}")
            return None

    # TENTATIVA 1: JID original (mais preciso, funciona com LID e contatos salvos)
    response = disparar(jid_ou_numero)
    if response and response.status_code in [200, 201]:
        return True

    # TENTATIVA 2: Fallback (Telefone limpo da base de dados)
    if jid_alternativo and jid_alternativo != jid_ou_numero:
        print(f"🔄 Iniciando fallback para: {jid_alternativo}")
        response_alt = disparar(jid_alternativo)
        return response_alt and response_alt.status_code in [200, 201]

    return False


# ----------------------------------------------------------------
# 3. CONFIGURACAO CLINICA E QR CODE  
# ----------------------------------------------------------------
@login_required
def configuracao_clinica(request):
    import os
    import requests
    from django.shortcuts import get_object_or_404 # Certifique-se de importar isso

    # --- VALIDAÇÃO DE PERFIL / CLÍNICA ---
    try:
        profile = request.user.profile
        clinic = profile.clinic
    except AttributeError:
        messages.error(request, "Perfil de usuário não configurado corretamente.")
        return redirect('dashboard')

    if not clinic:
        messages.error(request, "Seu perfil não possui uma clínica vinculada.")
        return redirect('dashboard')

    # --- GARANTE CONFIGURAÇÕES ---
    config, _ = Configuracao.objects.get_or_create(clinic=clinic)
    config_whatsapp, _ = ConfiguracaoWhatsApp.objects.get_or_create(clinic=clinic)

    # --- VARIÁVEIS WHATSAPP ---
    base_url = os.getenv("EVOLUTION_API_URL_BASE", "https://api-clinica-whatsapp.onrender.com")
    api_key = os.getenv("EVOLUTION_API_KEY")
    qr_code = None

    # =========================================================
    # ======================== POST ============================
    # =========================================================
    if request.method == "POST":
        form_type = request.POST.get('form_type')
        print(f"--- DEBUG POST: Recebido form_type='{form_type}' ---")

        # -----------------------------------------------------
        # 1. NOVO DENTISTA
        # -----------------------------------------------------
        if form_type == 'novo_dentista':
            nome = request.POST.get('nome', '').strip()
            cro = request.POST.get('cro', '').strip()
            cor = request.POST.get('cor', '#3788d8')

            if nome:
                try:
                    Dentista.objects.create(
                        clinic=clinic,
                        nome=nome,
                        cro=cro,
                        cor_calendario=cor,
                        ativo=True
                    )
                    messages.success(request, f"Dentista {nome} adicionado com sucesso!")
                except Exception as e:
                    messages.error(request, f"Erro ao salvar dentista: {e}")
            else:
                messages.warning(request, "O nome do dentista é obrigatório.")
            return redirect('configuracao_clinica')

        # -----------------------------------------------------
        # 2. NOVO PROCEDIMENTO
        # -----------------------------------------------------
        elif form_type == 'novo_procedimento':
            nome = request.POST.get('nome', '').strip()
            duracao = request.POST.get('duracao', '30')
            valor_raw = request.POST.get('valor', '0').strip()
            valor_limpo = valor_raw.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')

            if nome:
                try:
                    valor_final = float(valor_limpo) if valor_limpo else 0.0
                    Procedimento.objects.create(
                        clinic=clinic,
                        nome=nome,
                        duracao_estimada=int(duracao) if duracao.isdigit() else 30,
                        valor_sugerido=valor_final,
                        ativo=True
                    )
                    messages.success(request, f"Procedimento '{nome}' cadastrado!")
                except Exception as e:
                    messages.error(request, f"Erro técnico: {e}")
            else:
                messages.warning(request, "O nome do procedimento é obrigatório.")
            return redirect('configuracao_clinica')

        # -----------------------------------------------------
        # 3. EXCLUIR DENTISTA (NOVO BLOCO)
        # -----------------------------------------------------
        elif form_type == 'excluir_dentista':
            dentista_id = request.POST.get('dentista_id')
            dentista = get_object_or_404(Dentista, id=dentista_id, clinic=clinic)
            try:
                dentista.ativo = False # Exclusão lógica
                dentista.save()
                messages.success(request, f"Dr(a). {dentista.nome} removido(a) com sucesso.")
            except Exception as e:
                messages.error(request, f"Erro ao remover: {e}")
            return redirect('configuracao_clinica')

        # -----------------------------------------------------
        # 4. EXCLUIR PROCEDIMENTO (NOVO BLOCO)
        # -----------------------------------------------------
        elif form_type == 'excluir_procedimento':
            proc_id = request.POST.get('procedimento_id')
            procedimento = get_object_or_404(Procedimento, id=proc_id, clinic=clinic)
            try:
                procedimento.ativo = False # Exclusão lógica
                procedimento.save()
                messages.success(request, f"Procedimento '{procedimento.nome}' removido.")
            except Exception as e:
                messages.error(request, f"Erro ao remover: {e}")
            return redirect('configuracao_clinica')


        # -----------------------------------------------------
        # 3. DADOS DA CLÍNICA (UNIFICADO)
        # -----------------------------------------------------
        elif form_type == 'clinica':
            form = ConfiguracaoForm(request.POST, request.FILES, instance=config)
            if form.is_valid():
                form.save()

                # SINCRONIZA CAMPOS DO MODEL CLINIC
                clinic.endereco = request.POST.get("endereco", clinic.endereco)
                clinic.telefone = request.POST.get("telefone", clinic.telefone)
                clinic.save()

                messages.success(request, "Configurações da clínica atualizadas!")
            else:
                print(f"ERROS FORM CLINICA: {form.errors}")
                messages.error(request, "Erro nos dados da clínica. Verifique os campos.")

            return redirect('configuracao_clinica')

        # -----------------------------------------------------
        # 4. CRIAR INSTÂNCIA WHATSAPP
        # -----------------------------------------------------
        elif form_type == 'criar_instancia':
            nome_raw = request.POST.get('nova_instancia_nome', f'clinica_{clinic.id}')
            nome_instancia = "".join(x for x in nome_raw if x.isalnum() or x == '_').lower()

            try:
                payload = {
                    "instanceName": nome_instancia,
                    "token": api_key,
                    "qrcode": True,
                    "integration": "WHATSAPP-BAILEYS"
                }

                res = requests.post(
                    f"{base_url}/instance/create",
                    json=payload,
                    headers={"apikey": api_key},
                    timeout=20
                )

                if res.status_code in [200, 201]:
                    config_whatsapp.instancia_nome = nome_instancia
                    config_whatsapp.status_conexao = 'disconnected'
                    config_whatsapp.save()
                    messages.success(request, f"Instância '{nome_instancia}' criada com sucesso!")
                else:
                    messages.error(request, f"Erro na API Evolution: {res.json().get('message', 'Erro desconhecido')}")
            except Exception as e:
                messages.error(request, f"Erro de conexão com o servidor de WhatsApp: {e}")

            return redirect('configuracao_clinica')

        # -----------------------------------------------------
        # 5. REINICIAR INSTÂNCIA
        # -----------------------------------------------------
        elif form_type == 'reiniciar_instancia':
            try:
                requests.post(
                    f"{base_url}/instance/restart/{config_whatsapp.instancia_nome}",
                    headers={"apikey": api_key},
                    timeout=15
                )
                messages.info(request, "Reiniciando instância... O QR Code aparecerá em instantes.")
            except Exception as e:
                messages.error(request, f"Erro ao reiniciar: {e}")

            return redirect('configuracao_clinica')

        # -----------------------------------------------------
        # 6. DESCONECTAR WHATSAPP
        # -----------------------------------------------------
        elif form_type == 'desconectar_whatsapp':
            try:
                res = requests.delete(
                    f"{base_url}/instance/logout/{config_whatsapp.instancia_nome}",
                    headers={"apikey": api_key},
                    timeout=15
                )

                if res.status_code == 200:
                    config_whatsapp.status_conexao = 'disconnected'
                    config_whatsapp.save()
                    messages.success(request, "WhatsApp desconectado!")
            except Exception as e:
                messages.error(request, f"Erro ao desconectar: {e}")

            return redirect('configuracao_clinica')

        # -----------------------------------------------------
        # 7. DELETAR INSTÂNCIA
        # -----------------------------------------------------
        elif form_type == 'deletar_instancia':
            try:
                requests.delete(
                    f"{base_url}/instance/delete/{config_whatsapp.instancia_nome}",
                    headers={"apikey": api_key},
                    timeout=15
                )

                config_whatsapp.instancia_nome = None
                config_whatsapp.status_conexao = 'disconnected'
                config_whatsapp.save()

                messages.warning(request, "Instância removida permanentemente.")
            except Exception as e:
                messages.error(request, f"Erro ao deletar: {e}")

            return redirect('configuracao_clinica')

        # -----------------------------------------------------
        # 8. CONFIG WHATSAPP (MENSAGENS)
        # -----------------------------------------------------
        elif form_type == 'whatsapp':
            config_whatsapp.lembretes_ativos = 'lembretes_ativos' in request.POST
            config_whatsapp.fidelizacao_ativa = 'fidelizacao_ativa' in request.POST

            config_whatsapp.mensagem_confirmacao = request.POST.get('mensagem_confirmacao')
            config_whatsapp.mensagem_retorno = request.POST.get('mensagem_retorno')
            config_whatsapp.mensagem_sucesso_confirmacao = request.POST.get('mensagem_sucesso_confirmacao')
            config_whatsapp.mensagem_solicitacao_reagendamento = request.POST.get('mensagem_solicitacao_reagendamento')

            config_whatsapp.save()
            messages.success(request, "Configurações de automação salvas!")

            return redirect('configuracao_clinica')

    # =========================================================
    # ========================= GET ============================
    # =========================================================

    # --- DENTISTAS / PROCEDIMENTOS ---
    dentistas = Dentista.objects.filter(clinic=clinic, ativo=True).order_by('nome')
    procedimentos = Procedimento.objects.filter(clinic=clinic, ativo=True).order_by('nome')

    # --- STATUS WHATSAPP + QR CODE ---
    if config_whatsapp.instancia_nome:
        try:
            status_res = requests.get(
                f"{base_url}/instance/connectionState/{config_whatsapp.instancia_nome}",
                headers={"apikey": api_key},
                timeout=10
            )

            if status_res.status_code == 200:
                estado = status_res.json().get('instance', {}).get('state')
                config_whatsapp.status_conexao = 'connected' if estado == 'open' else 'disconnected'

                if config_whatsapp.status_conexao == 'disconnected':
                    qr_res = requests.get(
                        f"{base_url}/instance/connect/{config_whatsapp.instancia_nome}",
                        headers={"apikey": api_key},
                        timeout=10
                    )

                    if qr_res.status_code == 200:
                        qr_code = qr_res.json().get('base64')

                config_whatsapp.save()
        except Exception as e:
            print(f"⚠️ Erro ao sincronizar status do WhatsApp: {e}")

    # --- FORM ---
    form = ConfiguracaoForm(instance=config)

    return render(request, 'home/configuracao_clinica.html', {
        'form': form,
        'config': config,
        'clinic': clinic,
        'dentistas': dentistas,
        'procedimentos': procedimentos,
        'config_whatsapp': config_whatsapp,
        'qr_code': qr_code,
        'plano_pro': True
    })

# ----------------------------------------------------------------
# 4. PAINEL DE MONITORAMENTO DE LEMBRETES (Sincronizado com URLs)
# ----------------------------------------------------------------


@login_required
def painel_lembretes(request):
    clinic = request.user.profile.clinic

    # 🔥 HORA: Trabalhando com o fuso local para contadores precisos
    agora_local = timezone.localtime(timezone.now())
    hoje = agora_local.date()

    # --- NOVO: BUSCA DE ANIVERSARIANTES ---
    aniversariantes = Paciente.objects.filter(
        clinic=clinic,
        data_nascimento__day=hoje.day,
        data_nascimento__month=hoje.month
    )

    # --- Lógica de Final de Semana Inteligente ---
    if hoje.weekday() == 4:
        amanha = hoje + timedelta(days=3)
        label_proximo = "Segunda-feira"
    elif hoje.weekday() == 5:
        amanha = hoje + timedelta(days=2)
        label_proximo = "Segunda-feira"
    else:
        amanha = hoje + timedelta(days=1)
        label_proximo = "Amanhã"

    # Captura a data do filtro (Histórico)
    data_filtro_str = request.GET.get('data_historico')
    data_filtro = hoje
    if data_filtro_str:
        try:
            data_filtro = datetime.strptime(data_filtro_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            data_filtro = hoje

    # Contadores
    confirmados_hoje = Consulta.objects.filter(
        clinic=clinic, status='confirmada', data_hora__date=hoje).count()

    confirmados_amanha = Consulta.objects.filter(
        clinic=clinic, status='confirmada', data_hora__date=amanha).count()

    pendentes_count = Consulta.objects.filter(
        clinic=clinic, status='reagendamento_pendente').count()

    # Logs do dia selecionado
    logs_historico = LembreteLog.objects.filter(
        consulta__clinic=clinic,
        data_envio__date=data_filtro
    ).select_related('consulta', 'consulta__paciente').order_by('-data_envio')

    return render(request, 'home/painel_lembretes.html', {
        'confirmados_hoje': confirmados_hoje,
        'confirmados_amanha': confirmados_amanha,
        'label_proximo': label_proximo,
        'pendentes': pendentes_count,
        'logs': logs_historico,
        'data_filtro': data_filtro.strftime('%Y-%m-%d'),
        'hoje_real': hoje,
        'aniversariantes': aniversariantes,  # Enviando a lista para o template
    })


@login_required
def enviar_mensagem_manual(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            paciente_id = data.get('paciente_id')
            texto = data.get('mensagem')

            if not texto:
                return JsonResponse({'success': False, 'error': 'Mensagem vazia.'})

            # 1. Trava Multi-tenant
            paciente = get_object_or_404(
                Paciente, id=paciente_id, clinic=request.user.profile.clinic)

            # 2. Configuração
            config = ConfiguracaoWhatsApp.objects.filter(
                clinic=paciente.clinic).first()

            if not config or not config.instancia_nome:
                return JsonResponse({'success': False, 'error': 'WhatsApp não configurado.'})

            # 3. Disparo (Usando a função do utils.py que criamos)
            destinatario = paciente.whatsapp_jid or paciente.telefone

            # Note o retornar_json=True para pegarmos o message_id
            sucesso, resposta_api = enviar_mensagem_whatsapp(
                config=config,
                jid_ou_numero=destinatario,
                texto=texto,
                retornar_json=True
            )

            if sucesso:
                # 4. Captura o ID da mensagem para o histórico
                msg_id_api = None
                if resposta_api:
                    # Tenta pegar de 'messageId' ou 'key.id' dependendo da versão da Evolution
                    data_res = resposta_api[0] if isinstance(
                        resposta_api, list) else resposta_api
                    msg_id_api = data_res.get('key', {}).get(
                        'id') or data_res.get('messageId')

                # 5. Registro de Log
                ultima_consulta = Consulta.objects.filter(
                    paciente=paciente).order_by('-data_hora').first()

                LembreteLog.objects.create(
                    consulta=ultima_consulta,
                    status_envio='enviado',
                    mensagem_corpo=texto,  # Removi o prefixo para ficar limpo no balão de chat
                    tipo="Manual",
                    message_id=msg_id_api  # <-- AGORA VAI APARECER O CHECK DUPLO NO PAINEL!
                )
                return JsonResponse({'success': True})

            return JsonResponse({'success': False, 'error': 'Falha na Evolution API.'})

        except Exception as e:
            print(f"🚨 ERRO ENVIO MANUAL: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False}, status=405)


@login_required
def disparar_robo_lembretes(request):
    """
    Executa manualmente o comando de envio de lembretes em massa.
    """
    # Apenas administradores da clínica deveriam poder disparar o robô manualmente
    if not request.user.is_staff and not hasattr(request.user.profile, 'clinic'):
        messages.error(request, "Acesso negado.")
        return redirect('painel_lembretes')

    try:
        # Chama o Command do Django
        from django.core.management import call_command
        call_command('enviar_lembretes')

        messages.success(
            request, "🚀 O robô de lembretes terminou o processamento! Verifique a lista de logs abaixo.")
    except Exception as e:
        messages.error(request, f"💥 Houve um erro ao rodar o robô: {str(e)}")

    return redirect('painel_lembretes')


# ----------------------------------------------------------------
# 4. Inteligencia Artificial - Fidelização Otimizada
# ----------------------------------------------------------------


logger = logging.getLogger(__name__)


@login_required
def lista_fidelizacao(request):
    """
    View Principal: Exibe os dados persistidos no banco.
    Sincronizada com fidelizacao.html e o modelo HistoricoFidelizacao.
    """
    clinic = request.user.profile.clinic
    hoje = timezone.now().date()

    # 1. BUSCA DADOS JÁ EXISTENTES (Filtramos apenas pendentes para as tabelas principais)
    analises_pendentes = HistoricoFidelizacao.objects.filter(
        clinic=clinic,
        status='pendente'
    ).select_related('paciente').order_by('-data_analise')

    pacientes_retorno = []
    pacientes_alerta = []
    pacientes_risco = []

    for item in analises_pendentes:
        paciente = item.paciente

        # Busca a última consulta para calcular os dias de ausência
        ultima_con = Consulta.objects.filter(
            paciente=paciente).order_by('-data_hora').first()
        dias_ausente = (hoje - ultima_con.data_hora.date()
                        ).days if ultima_con else 0

        # Monta o dicionário que o template espera (p.nome, p.reasoning, p.id, etc)
        data_p = {
            'id': paciente.id,
            'nome': paciente.nome,
            'dias_ausente': dias_ausente,
            'reasoning': item.insight,   # No HTML você usa {{ p.reasoning }}
            'historico_id': item.id,     # Usado no JS para mudar o status
            'telefone': paciente.telefone
        }

        if item.categoria == 'risco':
            pacientes_risco.append(data_p)
        elif item.categoria == 'alerta':  # Adicionamos o tratamento para o amarelo
            pacientes_alerta.append(data_p)
        else:
            pacientes_retorno.append(data_p)

    # 2. GESTÃO DE NOTIFICAÇÕES (Sincronizado com {% for nota in notifications_ia %})
    notifications_ia = []  # Variável em inglês para bater com o HTML

    if pacientes_retorno:
        notifications_ia.append({
            "tipo": "retorno",
            "msg": f"Você tem {len(pacientes_retorno)} oportunidades de retorno precoce."
        })

    if pacientes_alerta:
        notifications_ia.append({
            "tipo": "alerta",
            "msg": f"Existem {len(pacientes_alerta)} pacientes em atraso preventivo (6-12 meses)."
        })

    if pacientes_risco:
        notifications_ia.append({
            "tipo": "perigo",
            "msg": f"Atenção! {len(pacientes_risco)} pacientes em risco crítico detectados."
        })

    # Aniversariantes do dia
    niver_hoje = Paciente.objects.filter(
        clinic=clinic,
        data_nascimento__day=hoje.day,
        data_nascimento__month=hoje.month
    ).count()

    if niver_hoje > 0:
        notifications_ia.append({
            "tipo": "niver",
            "msg": f"Hoje é aniversário de {niver_hoje} paciente(s)! Ótima chance para fidelizar."
        })

   # 3. HISTÓRICO SEGMENTADO (Para a segunda aba de acompanhamento)
    # Buscamos os 5 mais recentes de cada categoria para totalizar os 15 do Mix Temporal
    h_risco = HistoricoFidelizacao.objects.filter(clinic=clinic, categoria='risco')\
        .select_related('paciente').order_by('-data_analise')[:5]

    h_alerta = HistoricoFidelizacao.objects.filter(clinic=clinic, categoria='alerta')\
        .select_related('paciente').order_by('-data_analise')[:5]

    h_retorno = HistoricoFidelizacao.objects.filter(clinic=clinic, categoria='retorno')\
        .select_related('paciente').order_by('-data_analise')[:5]

    # 4. RENDERIZAÇÃO
    context = {
        # Dados para a Aba 1 (Dicionários formatados)
        'pacientes_risco': pacientes_risco,
        'pacientes_alerta': pacientes_alerta,
        'pacientes_retorno': pacientes_retorno,

        # Dados para a Aba 2 (Objetos do Model para as 3 tabelas de acompanhamento)
        'h_risco': h_risco,
        'h_alerta': h_alerta,
        'h_retorno': h_retorno,

        'notifications_ia': notifications_ia,

        # Cálculo do total considerando as 3 prateleiras
        'total_analisados': len(pacientes_risco) + len(pacientes_alerta) + len(pacientes_retorno)
    }

    return render(request, 'home/fidelizacao.html', context)


logger = logging.getLogger(__name__)


@login_required
@transaction.atomic
def gerar_analise_completa(request):
    """
    Processa a análise em massa via IA (Llama 3.3 70B) segmentada por Mix Temporal.
    Envia 15 pacientes de cada prateleira (Crítico, Alerta, Retorno) para o AIService.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método não permitido'}, status=405)

    clinic = request.user.profile.clinic
    hoje = timezone.now().date()
    hoje_datetime = timezone.now()

    try:
        # 1. Filtros de exclusão (Segurança)
        agendados_futuro = Consulta.objects.filter(
            clinic=clinic,
            data_hora__date__gt=hoje
        ).values_list('paciente_id', flat=True)

        em_tratamento = HistoricoFidelizacao.objects.filter(
            clinic=clinic,
            status__in=['contatado', 'recusou', 'ignorar', 'agendado']
        ).values_list('paciente_id', flat=True)

        # 2. Query Base
        base_query = Consulta.objects.filter(clinic=clinic) \
            .exclude(paciente_id__in=agendados_futuro) \
            .exclude(paciente_id__in=em_tratamento) \
            .values('paciente__id', 'paciente__nome', 'paciente__telefone') \
            .annotate(
                ultima_data=Max('data_hora'),
                historico_completo=StringAgg(
                    'observacoes', delimiter=' | ', ordering='-data_hora')
        )

        # 3. Construção do Mix Temporal (15 de cada para o Payload)
        q_longa = base_query.filter(
            ultima_data__date__lt=hoje - timedelta(days=365)).order_by('-ultima_data')[:5]
        q_media = base_query.filter(
            ultima_data__date__range=[
                hoje - timedelta(days=365), hoje - timedelta(days=180)]
        ).order_by('-ultima_data')[:5]
        q_recente = base_query.filter(
            ultima_data__date__range=[
                hoje - timedelta(days=180), hoje - timedelta(days=90)]
        ).order_by('-ultima_data')[:5]

        candidatos_unidos = list(q_longa) + list(q_media) + list(q_recente)

        if not candidatos_unidos:
            return JsonResponse({'success': True, 'total': 0, 'msg': 'Nenhum paciente novo para analisar.'})

        # Mapeamento para persistência
        dados_originais_map = {c['paciente__id']: c for c in candidatos_unidos}

        payload_para_ia = [{
            "id": c['paciente__id'],
            "nome": c['paciente__nome'],
            "dias": (hoje - c['ultima_data'].date()).days,
            "historico": str(c['historico_completo'])[:400] if c['historico_completo'] else "Sem observações",
        } for c in candidatos_unidos]

        # 4. Chamada ao AIService (Retorna: critico, alerta, retorno)
        ai = AIService()
        analise_ia = ai.analisar_estrategias_fidelizacao(payload_para_ia)

        # 5. Limpeza de pendentes e Persistência
        HistoricoFidelizacao.objects.filter(
            clinic=clinic, status='pendente').delete()

        objetos_para_criar = []

        # Mapeamento: (Chave vinda da IA -> Categoria no nosso Model)
        # 'critico' vai para a tabela vermelha (risco), os outros para as demais (retorno)
        mapeamento_categorias = [
            ('critico', 'risco'),
            ('alerta', 'alerta'),
            ('retorno', 'retorno')
        ]

        for chave_ia, categoria_model in mapeamento_categorias:
            pacientes_set = analise_ia.get(chave_ia, [])

            for item in pacientes_set:
                try:
                    p_id_int = int(item.get('id'))
                except (ValueError, TypeError):
                    continue

                if p_id_int in dados_originais_map:
                    p_orig = dados_originais_map[p_id_int]
                    reasoning_texto = item.get(
                        'reasoning', "Análise técnica pendente.")

                    # Gera o texto do WhatsApp baseado no reasoning específico da prateleira
                    abordagem_whatsapp = ai.gerar_insight_fidelizacao(
                        nome_paciente=p_orig['paciente__nome'],
                        dias_ausente=(
                            hoje - p_orig['ultima_data'].date()).days,
                        historico=str(p_orig['historico_completo'])[:100],
                        reasoning=reasoning_texto
                    )

                    objetos_para_criar.append(
                        HistoricoFidelizacao(
                            clinic=clinic,
                            paciente_id=p_id_int,
                            insight=reasoning_texto,
                            insight_whatsapp=abordagem_whatsapp,
                            categoria=categoria_model,
                            status='pendente',
                            data_analise=hoje_datetime  # Use o nome correto do seu campo de data
                        )
                    )

        if objetos_para_criar:
            HistoricoFidelizacao.objects.bulk_create(objetos_para_criar)
            return JsonResponse({
                'success': True,
                'total': len(objetos_para_criar),
                'msg': f'Processado com sucesso: {len(objetos_para_criar)} pacientes analisados.'
            })

        return JsonResponse({'success': False, 'error': 'A IA não retornou dados válidos.'}, status=500)

    except Exception as e:
        logger.error(
            f"Erro Crítico no processamento IA: {traceback.format_exc()}")
        return JsonResponse({'success': False, 'error': "Erro interno ao processar análise."}, status=500)


@login_required
def buscar_insight_ia(request, paciente_id):
    """
    Gera o script de WhatsApp usando o reasoning técnico como base.
    """
    clinic = request.user.profile.clinic
    # Garante que o paciente pertence à clínica
    paciente = get_object_or_404(Paciente, id=paciente_id, clinic=clinic)

    # Capturamos o reasoning que veio do clique no botão (passado via JS)
    reasoning_previo = request.GET.get('reasoning', '')

    try:
        # Pega as últimas 3 consultas para dar contexto de "histórico rico"
        consultas = Consulta.objects.filter(
            paciente=paciente, clinic=clinic).order_by('-data_hora')[:3]
        historico_rich = " | ".join(
            [c.observacoes for c in consultas if c.observacoes])

        if not consultas.exists():
            return JsonResponse({'success': False, 'error': 'Paciente sem histórico.'}, status=400)

        ultima_visita = consultas[0]
        dias = (timezone.now() - ultima_visita.data_hora).days

        # Chama o serviço local (Mac M5 voando!)
        ai_service = AIService()
        script = ai_service.gerar_insight_fidelizacao(
            nome_paciente=paciente.nome,
            dias_ausente=dias,
            historico=historico_rich[:400],
            reasoning=reasoning_previo
        )

        return JsonResponse({'success': True, 'insight': script})
    except Exception as e:
        logger.error(f"Erro no insight individual: {traceback.format_exc()}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def mudar_status_fidelizacao(request, historico_id):
    """
    Atualiza o status de um insight da IA (contatado, ignorar, etc).
    """
    if request.method == 'POST':
        item = get_object_or_404(
            HistoricoFidelizacao,
            id=historico_id,
            clinic=request.user.profile.clinic
        )
        novo_status = request.POST.get('status')

        # Lista de status permitidos para evitar lixo no banco
        status_validos = ['contatado', 'recusou',
                          'ignorar', 'agendado', 'pendente']

        if novo_status in status_validos:
            item.status = novo_status
            item.save()
            return JsonResponse({'success': True})

    return JsonResponse({'success': False, 'error': 'Método inválido ou status incorreto'}, status=400)


logger = logging.getLogger(__name__)


@login_required
def preview_dados_ia(request):
    """
    View de Debug Sincronizada: Mantém o payload único e adiciona as listas separadas 
    para as 3 prateleiras (Crítico, Alerta e Retorno).
    """
    try:
        clinic = request.user.profile.clinic
        hoje_date = timezone.now().date()

        # 1. Filtros de Exclusão (Segurança)
        agendados_futuro = Consulta.objects.filter(
            clinic=clinic,
            data_hora__date__gt=hoje_date
        ).values_list('paciente_id', flat=True)

        em_tratamento = HistoricoFidelizacao.objects.filter(
            clinic=clinic,
            status__in=['contatado', 'recusou', 'ignorar', 'agendado']
        ).values_list('paciente_id', flat=True)

        # --- FUNÇÃO AUXILIAR DE PROCESSAMENTO ---
        def filtrar_e_classificar(queryset, limite):
            lista_local = []
            for c in queryset[:limite]:
                hist_texto = (c['historico_completo'] or "").lower()

                perfil = "Clínico Geral"
                peso_clinico = 1.0

                if any(word in hist_texto for word in ['orto', 'hyrax', 'bimotor', 'manutenção', 'braquete', 'aparelho']):
                    perfil = "Ortodontia"
                    peso_clinico = 3.0
                elif any(word in hist_texto for word in ['limpeza', 'profilaxia', 'raspagem', 'tártaro', 'flúor']):
                    perfil = "Prevenção/Periodontia"
                    peso_clinico = 2.0
                elif any(word in hist_texto for word in ['moldagem', 'prótese', 'coroa', 'pino', 'implante', 'provisório']):
                    perfil = "Reabilitação/Prótese"
                    peso_clinico = 2.5

                dias_ausente = (hoje_date - c['ultima_data'].date()).days
                score_urgencia = peso_clinico * dias_ausente

                lista_local.append({
                    "id": c['paciente__id'],
                    "nome": c['paciente__nome'],
                    "perfil": perfil,
                    "urgencia": round(score_urgencia, 1),
                    "dias": dias_ausente,
                    "ultimo_procedimento": hist_texto.split('|')[0].strip().capitalize() if hist_texto else "Não registrado",
                    "historico": hist_texto[:400].strip(),
                    "telefone": c['paciente__telefone']
                })
            return lista_local

        # 2. Query Base
        base_query = Consulta.objects.filter(clinic=clinic) \
            .exclude(paciente_id__in=agendados_futuro) \
            .exclude(paciente_id__in=em_tratamento) \
            .values('paciente__id', 'paciente__nome', 'paciente__telefone') \
            .annotate(
                ultima_data=Max('data_hora'),
                historico_completo=StringAgg(
                    'observacoes', delimiter=' | ', ordering='-data_hora')
        )

        # 3. Execução das 3 Prateleiras
        # A: > 365 dias
        q_longa = base_query.filter(
            ultima_data__date__lt=hoje_date - timedelta(days=365)).order_by('-ultima_data')
        shelf_longa = filtrar_e_classificar(q_longa, 15)

        # B: 180 a 365 dias
        q_media = base_query.filter(
            ultima_data__date__range=[
                hoje_date - timedelta(days=365), hoje_date - timedelta(days=180)]
        ).order_by('-ultima_data')
        shelf_media = filtrar_e_classificar(q_media, 15)

        # C: 90 a 180 dias
        q_recente = base_query.filter(
            ultima_data__date__range=[
                hoje_date - timedelta(days=180), hoje_date - timedelta(days=90)]
        ).order_by('-ultima_data')
        shelf_recente = filtrar_e_classificar(q_recente, 15)

        # 4. Payload Final (Para o loop único que já funciona)
        payload_final = shelf_longa + shelf_media + shelf_recente
        payload_final = sorted(
            payload_final, key=lambda x: x['urgencia'], reverse=True)

        # 5. Dicionário de Contexto
        contexto = {
            'dados_para_ia': payload_final,  # Mantido para não quebrar seu HTML atual

            # NOVAS LISTAS SEPARADAS (Para as 3 tabelas que vamos usar)
            'pacientes_risco': shelf_longa,   # Críticos (>365d)
            'pacientes_alerta': shelf_media,  # Atenção (180-365d)
            'pacientes_retorno': shelf_recente,  # Recentes (90-180d)

            'total': len(payload_final),
            'data_geracao': hoje_date,
            'filtros_aplicados': 'Mix Temporal Ativo: 3 Faixas de Retenção.',

            'count_orto': sum(1 for p in payload_final if p['perfil'] == "Ortodontia"),
            'count_prev': sum(1 for p in payload_final if p['perfil'] == "Prevenção/Periodontia"),
            'count_protese': sum(1 for p in payload_final if p['perfil'] == "Reabilitação/Prótese"),

            'count_90': len(shelf_recente),
            'count_180': len(shelf_media),
            'count_365': len(shelf_longa),
        }

        return render(request, 'home/debug/payload_ia.html', contexto)

    except Exception as e:
        logger.error(f"Erro no preview_dados_ia: {traceback.format_exc()}")
        return HttpResponse(f"Erro ao processar payload: {str(e)}", status=500)


@login_required
@transaction.atomic
def limpar_analises_pendentes(request):
    """
    Limpa o lixo e as sugestões pendentes para permitir uma nova análise limpa.
    """
    if request.method == 'POST':
        try:
            clinic = request.user.profile.clinic

            # Deletamos apenas os registros com status 'pendente'
            deleted_count, _ = HistoricoFidelizacao.objects.filter(
                clinic=clinic,
                status='pendente'
            ).delete()

            logger.info(
                f"Limpeza realizada: {deleted_count} registros removidos para clínica {clinic.nome}")

            return JsonResponse({
                'success': True,
                'deleted': deleted_count,
                'message': 'Sugestões pendentes limpas com sucesso.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'success': False, 'error': 'Método não permitido'}, status=405)


def registro_clinica_view(request):
    if request.method == 'POST':
        # 1. Captura os dados do formulário
        nome_completo = request.POST.get('nome_completo')
        username = request.POST.get('username')
        email = request.POST.get('email_comercial')
        password = request.POST.get('password')
        clinic_nome = request.POST.get('clinica_nome')
        whatsapp = request.POST.get('whatsapp')

        # 2. Cria o Usuário (Dono)
        # O post_save do User já cria o Profile vazio via Signal
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=nome_completo
        )

        # 3. Cria a Clínica
        # O seu Signal 'vincular_dono_ao_profile' no models.py
        # vai detectar isso e amarrar o User, a Clinic e o Profile sozinhos!
        Clinic.objects.create(
            dono=user,
            nome=clinic_nome,
            telefone=whatsapp
        )

        # 4. Faz o login e redireciona
        login(request, user)
        return redirect('dashboard')

    return render(request, 'home/registro_clinica.html')


def planos_view(request):
    return render(request, 'home/planos.html')




@login_required
def criar_pagamento(request):
    # Pegamos o plano e o ciclo (mensal/anual) que vem do Modal
    plano_nome = request.GET.get('plano', 'essential').lower()
    ciclo = request.GET.get('ciclo', 'mensal').lower()

    # TABELA DE PREÇOS OFICIAL (Blindada no Backend)
    # Valores: 99 e 149 (com 20% de desconto no anual total)
    TABELA_PRECOS = {
        'essential': {
            'mensal': 99.00,
            'anual': 950.40,  # 79.20 * 12
        },
        'professional': {
            'mensal': 149.00,
            'anual': 1430.40, # 119.20 * 12
        }
    }

    # Busca o valor real. Se não achar, usa o Essential Mensal por segurança.
    try:
        valor = TABELA_PRECOS[plano_nome][ciclo]
    except KeyError:
        valor = 99.00
        plano_nome = 'essential'
        ciclo = 'mensal'

    # SDK com seu Access Token
    sdk = mercadopago.SDK("APP_USR-2955715257905203-021720-c6a2e4ee5bb6533e5cc13b14f6167b33-6575177")

    # Pegamos a clínica associada (Inquilino)
    clinica = getattr(request.user, 'minha_clinica', None)
    if not clinica:
        messages.error(request, "Erro: Clínica não identificada.")
        return redirect('dashboard')

    # Montagem dos dados para o Mercado Pago
    titulo_plano = f"OdontoClinics {plano_nome.upper()} ({ciclo.upper()})"
    
    preference_data = {
        "items": [
            {
                "id": f"{plano_nome}_{ciclo}",
                "title": titulo_plano,
                "quantity": 1,
                "unit_price": float(valor),
                "currency_id": "BRL"
            }
        ],
        "payer": {
            "email": request.user.email,
            "first_name": request.user.first_name,
        },
        "back_urls": {
            "success": "https://www.odontoclinics.com/dashboard/?status=success",
            "failure": "https://www.odontoclinics.com/planos/?status=failure",
            "pending": "https://www.odontoclinics.com/planos/?status=pending"
        },
        "auto_return": "approved",
        # Passamos o ID da clínica e o plano para o Webhook saber quem liberar
        "external_reference": f"clinica_{clinica.id}_{plano_nome}_{ciclo}",
        "notification_url": "https://www.odontoclinics.com/webhooks/mercadopago/",
    }

    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]

        # Redireciona para o checkout do Mercado Pago
        return redirect(preference["init_point"])
    except Exception as e:
        print(f"Erro MP: {e}")
        messages.error(request, "Erro ao conectar com o Mercado Pago.")
        return redirect('planos')


@csrf_exempt
def mercado_pago_webhook(request):
    # Dica: Mova o Token para o settings.py ou .env no Render para segurança
    access_token = os.getenv("MERCADO_PAGO_TOKEN", "SEU_TOKEN_AQUI")
    sdk = mercadopago.SDK(access_token)

    data = {}
    if request.body:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            pass

    # Captura robusta do ID e Tipo
    resource_id = data.get("data", {}).get("id") or request.GET.get("id")
    topic = data.get("type") or request.GET.get("topic")

    if (topic == "payment" or topic == "payment.updated") and resource_id:
        payment_info = sdk.payment().get(resource_id)

        if payment_info.get("status") == 200:
            payment_data = payment_info["response"]
            payment_status = payment_data.get("status")
            clinic_id = payment_data.get("external_reference")
            
            # Pegamos o ID do pagamento no MP para evitar duplicidade (Idempotência)
            mp_payment_id = str(payment_data.get("id"))

            if payment_status == "approved" and clinic_id:
                try:
                    clinica = Clinic.objects.get(id=clinic_id)
                    
                    # --- TRAVA DE DUPLICIDADE ---
                    # Verifique se este pagamento já foi processado antes de somar dias
                    # Se você não tiver um campo para isso, considere criar um model 'Pagamento'
                    # ----------------------------

                    # 1. Lógica de upgrade de plano
                    try:
                        item_title = payment_data["additional_info"]["items"][0]["title"].upper()
                        clinica.plano = 'professional' if "PROFESSIONAL" in item_title else 'essential'
                    except (KeyError, IndexError):
                        clinica.plano = 'essential' # Fallback seguro

                    # 2. Renovação de Datas
                    hoje = timezone.now()
                    # Se a clínica já está ativa e a data é futura, somamos à data atual dela
                    if clinica.data_expiracao_teste and clinica.data_expiracao_teste > hoje:
                        clinica.data_expiracao_teste += timedelta(days=30)
                    else:
                        clinica.data_expiracao_teste = hoje + timedelta(days=30)

                    clinica.ativo = True
                    clinica.save()

                    # 3. Disparo de E-mail de Boas-vindas
                    # O try/except já está dentro da função enviar_email_boas_vindas,
                    # então aqui o fluxo segue limpo.
                    enviar_email_boas_vindas(clinica)

                    return HttpResponse(status=200)
                except Clinic.DoesNotExist:
                    return HttpResponse("Clínica não encontrada", status=200) # MP exige 200 para parar de tentar

    return HttpResponse(status=200)


def enviar_email_boas_vindas(clinica):
    """Função auxiliar para manter o webhook limpo e garantir entrega"""
    try:
        # 1. Garantir que os dados existam para não quebrar o render_to_string
        contexto = {
            'nome_usuario': clinica.usuario.get_full_name() or clinica.usuario.username,
            'nome_clinica': clinica.nome_clinica or "sua clínica",
            'plano': clinica.plano.upper() if clinica.plano else "Pro"
        }

        # 2. Renderizar o novo HTML com CSS Inline (aquele que enviamos com tabelas)
        html_content = render_to_string('emails/boas_vindas_plano.html', contexto)
        text_content = strip_tags(html_content)

        # 3. Configurar o e-mail
        # Dica: Evite começar o assunto com Emojis em domínios novos para não pontuar como Spam
        subject = f"Bem-vindo à OdontoClinics - Plano {contexto['plano']} Ativo"
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL, # suporte@odontoclinics.com
            to=[clinica.usuario.email],
            reply_to=['suporte@odontoclinics.com'], # Ajuda a validar que você é real
        )
        
        email.attach_alternative(html_content, "text/html")
        
        # 4. Envio
        email.send(fail_silently=False)
        
    except Exception as e:
        # Importante: No Render, o print(e) aparecerá nos logs do Dashboard
        print(f"Erro crítico no disparo de e-mail: {e}")







def upload_arquivo_paciente(request, paciente_id):
    if request.method == 'POST' and request.FILES.get('arquivo'):
        try:
            paciente = Paciente.objects.get(id=paciente_id)
            
            # Cria o registro no banco e salva o arquivo na pasta /media/
            novo_arquivo = ArquivoPaciente.objects.create(
                paciente=paciente,
                arquivo=request.FILES.get('arquivo'),
                descricao=request.POST.get('descricao', 'Upload via Prontuário')
            )
            
            return JsonResponse({
                'success': True, 
                'url': novo_arquivo.arquivo.url, # URL para o preview
                'id': novo_arquivo.id
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Método inválido.'})


from django.views.decorators.http import require_POST

@require_POST
def deletar_arquivo_paciente(request, arquivo_id):
    arquivo = get_object_or_404(ArquivoPaciente, id=arquivo_id)
    # Opcional: deletar o arquivo físico do disco/Render também
    arquivo.arquivo.delete(save=False) 
    arquivo.delete()
    return JsonResponse({'success': True})