from django.urls import path
from django.contrib.auth import views as auth_views
from . import views


urlpatterns = [

    # -----------------------------
    # PÚBLICO
    # -----------------------------
    path('', views.homepage, name='homepage'),

    # -----------------------------
    # AUTENTICAÇÃO
    # -----------------------------
    path('login/', auth_views.LoginView.as_view(
        template_name='home/login.html'
    ), name='login'),

    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # -----------------------------
    # ÁREA INTERNA
    # -----------------------------
    path('index/', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('sobre/', views.sobre, name='sobre'),

    # -----------------------------
    # PACIENTES
    # -----------------------------
    path('pacientes/', views.lista_pacientes, name='lista_pacientes'),
    path('pacientes/novo/', views.novo_paciente, name='novo_paciente'),
    path('pacientes/editar/<int:id>/',
         views.editar_paciente, name='editar_paciente'),
    path('pacientes/excluir/<int:id>/',
         views.excluir_paciente, name='excluir_paciente'),
    path('pacientes/detalhes/<int:id>/',
         views.detalhes_paciente, name='detalhes_paciente'),

    path('pacientes/exportar/', views.exportar_pacientes,
         name='exportar_pacientes'),
    path('pacientes/importar/', views.importar_pacientes,
         name='importar_pacientes'),
    path('pacientes/baixar-modelo/',
         views.baixar_exemplo_pacientes, name='baixar_exemplo_pacientes'),


    path('verificar-cpf/', views.verificar_cpf_existente,
         name='verificar_cpf_existente'),

     path('pacientes/upload-arquivo/<int:paciente_id>/', views.upload_arquivo_paciente, name='upload_arquivo_paciente'),
     path('pacientes/deletar-arquivo/<int:arquivo_id>/', views.deletar_arquivo_paciente, name='deletar_arquivo_paciente'),

    # -----------------------------
    # CONSULTAS
    # -----------------------------
    path('agendar/', views.agendar, name='agendar'),
    path('consultas/detalhes/<int:id>/',
         views.detalhes_consulta, name='detalhes_consulta'),
    path('consultas/editar/<int:id>/',
         views.editar_consulta, name='editar_consulta'),
    path('consultas/excluir/<int:id>/',
         views.excluir_consulta, name='excluir_consulta'),

    # Listagem Geral
    path('consultas/lista/', views.lista_consultas, name='lista_consultas'),

    # NOVAS ROTAS: Importação e Exportação de Consultas
    path('consultas/exportar/', views.exportar_consultas,
         name='exportar_consultas'),
    path('consultas/importar/', views.importar_consultas,
         name='importar_consultas'),
    path('consultas/modelo/', views.baixar_modelo_consultas,
         name='baixar_modelo_consultas'),

    # Consultas do dia
    path('consultas-hoje/', views.consultas_hoje, name='consultas_hoje'),

    # Recibo
    path('consultas/recibo/<int:id>/',
         views.recibo_consulta, name='recibo_consulta'),

    path('recibo/<int:id>/pdf/', views.baixar_pdf_recibo, name='baixar_pdf_recibo'),
    path('consultas/em-aberto/', views.consultas_em_aberto,
         name='consultas_em_aberto'),
    path('agenda/reagendar-drag/', views.reagendar_drag, name='reagendar_drag'),

    # -----------------------------
    # FINANCEIRO
    # -----------------------------
    path('financeiro/', views.financeiro, name='financeiro'),
    path('financeiro/excluir/<int:id>/',
         views.excluir_financeiro, name='excluir_financeiro'),

    # -----------------------------
    # RELATÓRIOS
    # -----------------------------
    path('relatorios/', views.relatorios, name='relatorios'),

    # -----------------------------
    # USUÁRIOS E PERFIL
    # -----------------------------
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('usuarios/novo/', views.criar_usuario, name='criar_usuario'),
    path('usuarios/<int:user_id>/editar/',
         views.editar_usuario, name='editar_usuario'),
    path('meu-perfil/', views.meu_perfil, name='meu_perfil'),

    # -----------------------------
    # CONFIGURAÇÃO DA CLÍNICA & WHATSAPP
    # -----------------------------
    path('configuracoes/', views.configuracao_clinica,
         name='configuracao_clinica'),
    path('manual/', views.manual_operacao, name='manual_operacao'),
    path('painel-lembretes/', views.painel_lembretes, name='painel_lembretes'),
    path('experimentar-gratis/', views.registro_clinica_view, name='registro_clinica'),
        # Dentistas
    path('dentistas/', views.lista_dentistas, name='lista_dentistas'),
    path('dentistas/novo/', views.adicionar_dentista, name='adicionar_dentista'),
    
    # Procedimentos
    path('procedimentos/', views.lista_procedimentos, name='lista_procedimentos'),
    path('procedimentos/novo/', views.adicionar_procedimento, name='adicionar_procedimento'),


    # -----------------------------
    # WEBHOOK WHATSAPP (A URL GLOBAL)
    # -----------------------------
    path('webhook-whatsapp', views.webhook_whatsapp, name='webhook_whatsapp'),
    path('fidelizacao/', views.lista_fidelizacao, name='lista_fidelizacao'),

    # -----------------------------
    # FULLCALENDAR
    # -----------------------------
    path("agenda/events/", views.agenda_events, name="agenda_events"),
    path("agenda/", views.agenda, name="agenda"),

    # -----------------------------
    # GOOGLE CALENDAR
    # -----------------------------
    path("google/auth/", views.google_auth, name="google_auth"),
    path("google/callback/", views.google_callback, name="google_callback"),

    # -----------------------------
    # Whats App
    # -----------------------------

    path('enviar-mensagem-manual/', views.enviar_mensagem_manual,
         name='enviar_mensagem_manual'),

    # -----------------------------
    # Inteligência Artificial - OdontoClinics
    # -----------------------------

    # Rota Principal da Dashboard de Fidelização
    path('fidelizacao/', views.lista_fidelizacao, name='lista_fidelizacao'),

    # Processamento em Massa (Botão: Gerar Relatório com IA)
    path('fidelizacao/gerar-analise-completa/', views.gerar_analise_completa, name='gerar_analise_completa'),

    # Mudar status (Ignorar, Contatado, etc)
    path('fidelizacao/mudar-status/<int:historico_id>/', views.mudar_status_fidelizacao, name='mudar_status_fidelizacao'),

    # Geração de script individual para WhatsApp (Modal Abordar)
    path('ajax/insight-ia/<int:paciente_id>/', views.buscar_insight_ia, name='buscar_insight_ia'),

    # Debug do Payload (Acessar manualmente para ver o JSON)
    path('fidelizacao/preview-debug/', views.preview_dados_ia, name='preview_dados_ia'),
     path('fidelizacao/limpar/', views.limpar_analises_pendentes, name='limpar_fidelizacao'),
    


    # Seu urls.py (Trecho final)
    
    # -----------------------------
    # Outros Robôs e Pagamentos
    # -----------------------------
    path('disparar-robo/', views.disparar_robo_lembretes, name='disparar_robo'),
    path('planos/', views.planos_view, name='planos'),
    path('pagamento/criar/', views.criar_pagamento, name='criar_pagamento'),
    
    # Esta é a URL que o Mercado Pago vai "chamar"
    path('webhooks/mercadopago/', views.mercado_pago_webhook, name='mp_webhook'),
]
