from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

# -----------------------------
# CLÍNICA (TENANT)
# -----------------------------



class Clinic(models.Model):
    PLANOS = [
        ('essential', 'Essential'),
        ('professional', 'Professional'),
    ]

    # VINCULANDO AO DONO
    dono = models.OneToOneField(User, on_delete=models.CASCADE, related_name='minha_clinica')
    
    nome = models.CharField(max_length=150)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    plano = models.CharField(
        max_length=20, choices=PLANOS, default='essential')
    
    # LÓGICA DE TESTE E STATUS
    criado_em = models.DateTimeField(auto_now_add=True)
    data_expiracao_teste = models.DateTimeField(blank=True, null=True)
    ativo = models.BooleanField(default=True)

    # SEGURANÇA CONTRA DUPLICIDADE NO WEBHOOK
    ultimo_id_pagamento = models.CharField(max_length=100, blank=True, null=True)
    data_ultimo_pagamento = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Define a expiração apenas na criação (primeira vez)
        if not self.pk and not self.data_expiracao_teste:
            self.data_expiracao_teste = timezone.now() + timedelta(days=30)
        super(Clinic, self).save(*args, **kwargs)

    @property
    def dias_restantes(self):
        if self.data_expiracao_teste:
            delta = self.data_expiracao_teste - timezone.now()
            # Retorna 0 se o tempo já passou, evitando números negativos
            return max(0, delta.days)
        return 0

    @property
    def is_premium(self):
        """Verifica se a clínica possui o plano Professional e está dentro do prazo"""
        return self.plano == 'professional' and self.ativo and self.dias_restantes > 0

    @property
    def em_alerta_expiracao(self):
        """Retorna True se faltarem 5 dias ou menos para expirar"""
        return 0 < self.dias_restantes <= 5

    @property
    def status_pagamento(self):
        """Lógica centralizada para badges e cores no sistema"""
        if self.is_premium:
            return 'professional'
        if self.dias_restantes <= 0:
            return 'expirado'
        if self.em_alerta_expiracao:
            return 'alerta'
        return 'essential'

    @property
    def exibir_aviso_teste(self):
        """Define se o contador de dias aparece no Navbar"""
        # Se for Professional ativo, o aviso some
        if self.is_premium:
            return False
        # No Essential, mostra enquanto houver dias restantes
        return self.dias_restantes > 0

    def __str__(self):
        return f"{self.nome} ({self.get_plano_display()})"
    
    
# -----------------------------
# CONFIGURAÇÃO DE WHATSAPP (MULTI-TENANT)
# -----------------------------

class ConfiguracaoWhatsApp(models.Model):
    clinic = models.OneToOneField(
        Clinic, on_delete=models.CASCADE, related_name='whatsapp_config')

    # Integração Evolution API
    instancia_nome = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        default=None
    )
    instancia_token = models.CharField(max_length=255, blank=True, null=True)
    apikey_instancia = models.CharField(max_length=255, blank=True, null=True)

    status_conexao = models.CharField(max_length=20, default='disconnected', choices=[
        ('connected', 'Conectado'),
        ('disconnected', 'Desconectado'),
        ('connecting', 'Conectando...')
    ])

    # Lembretes de Consulta
    lembretes_ativos = models.BooleanField(default=False)
    tipo_envio = models.CharField(max_length=20, default='24h', choices=[
        ('24h', '24 horas antes'),
        ('8am', '08:00 da manhã do dia anterior'),
    ])

    # 1. Mensagem de Disparo (Pergunta)
    mensagem_confirmacao = models.TextField(
        default="Olá *{paciente}*, confirmamos sua consulta com Dr(a). {medico} para amanhã, dia {data} às {hora}? Digite SIM para confirmar ou NÃO para cancelar.",
        help_text="Tags: {paciente}, {medico}, {data}, {hora}, {clinica}"
    )

    # 2. Resposta automática após o paciente CONFIRMAR (SIM)
    mensagem_sucesso_confirmacao = models.TextField(
        default="Maravilha, *{paciente}*! 🙌\n\nSua consulta está confirmadíssima para {data_hora}.\nEstamos preparando tudo para te receber com muito carinho aqui na *{clinica}*.\n\nTenha um excelente dia! ✨",
        help_text="Tags: {paciente}, {data_hora}, {clinica}"
    )

    # 3. Resposta automática após o paciente CANCELAR/REAGENDAR (NÃO)
    mensagem_solicitacao_reagendamento = models.TextField(
        default="Entendido, *{paciente}*. Recebemos sua solicitação de reagendamento. Em breve nossa equipe entrará em contato para ajustar o melhor horário para você.",
        help_text="Tags: {paciente}, {clinica}"
    )

    # Regras
    permitir_reagendamento_auto = models.BooleanField(default=True)

    def __str__(self):
        return f"WhatsApp Config - {self.clinic.nome}"


# -----------------------------
# PROFILE (USUÁRIOS)
# -----------------------------

class Profile(models.Model):
    CARGOS = [
        ('admin', 'Administrador'),
        ('dentista', 'Dentista'),
        ('recepcao', 'Recepção'),
        ('financeiro', 'Financeiro'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    foto = models.ImageField(upload_to='perfil/', null=True, blank=True)
    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, null=True, blank=True)
    cargo = models.CharField(max_length=20, choices=CARGOS, default='admin')
    ativo = models.BooleanField(default=True)

    google_access_token = models.CharField(
        max_length=500, blank=True, null=True)
    google_refresh_token = models.CharField(
        max_length=500, blank=True, null=True)
    google_token_expiry = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} ({self.cargo})"


# -----------------------------
# CONFIGURAÇÃO VISUAL DA CLÍNICA
# -----------------------------

class Configuracao(models.Model):
    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE)
    nome_clinica = models.CharField(max_length=200, blank=True, null=True)
    nome_profissional = models.CharField(max_length=200, blank=True, null=True)
    cro = models.CharField(max_length=50, blank=True, null=True)
    documento_fiscal = models.CharField(max_length=25, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    assinatura_digital = models.ImageField(
        upload_to='assinaturas/', blank=True, null=True)

    def __str__(self):
        return f"Configuração de {self.clinic.nome}"


# -----------------------------
# PACIENTES
# -----------------------------

class Paciente(models.Model):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)
    nome = models.CharField(max_length=150)

    responsavel = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='dependentes')

    telefone = models.CharField(max_length=20, blank=True, null=True)

    telefone_limpo = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        db_index=True,
        help_text="Apenas números do telefone para busca rápida"
    )
    whatsapp_jid = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="ID único do WhatsApp (útil para resolver o problema de IDs @lid)"
    )

    email = models.EmailField(blank=True, null=True)
    cpf = models.CharField(max_length=14, blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)
    cep = models.CharField(max_length=9, blank=True, null=True)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    numero = models.CharField(max_length=10, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=2, blank=True, null=True)
    observacoes_clinicas = models.TextField(blank=True, null=True)
    data_cadastro = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('clinic', 'cpf')

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if self.telefone:
            # Garante que telefone_limpo contenha apenas dígitos para o Webhook
            self.telefone_limpo = "".join(
                filter(str.isdigit, str(self.telefone)))
        super(Paciente, self).save(*args, **kwargs)


# -----------------------------
# PROCEDIMENTOS
# -----------------------------

class Procedimento(models.Model):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)
    nome = models.CharField(max_length=100)
    duracao_estimada = models.PositiveIntegerField(default=30, help_text="Duração em minutos")
    valor_sugerido = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nome} ({self.clinic.nome})"

# -----------------------------
# DENTISTAS (PROFISSIONAIS)
# -----------------------------

class Dentista(models.Model):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)
    nome = models.CharField(max_length=150)
    cro = models.CharField(max_length=20, blank=True, null=True)
    cor_calendario = models.CharField(
        max_length=7, 
        default="#3788d8", 
        help_text="Cor para exibir no FullCalendar (Ex: #3788d8)"
    )
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return self.nome



# -----------------------------
# CONSULTAS
# -----------------------------

class Consulta(models.Model):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)
    paciente = models.ForeignKey(
        Paciente, on_delete=models.CASCADE, related_name='consultas')
    
    dentista = models.ForeignKey(
        Dentista, 
        on_delete=models.PROTECT, # Protege para não apagar dentista com agenda
        related_name='consultas',
        null=True, # Temporário para migração, depois pode remover
        blank=True
    )
    procedimento = models.ForeignKey(
        Procedimento, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='consultas'
    )

    responsavel = models.ForeignKey(
        Paciente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consultas_como_responsavel'
    )

    data_hora = models.DateTimeField()

    STATUS_CHOICES = [
        ('agendada', 'Agendada'),
        ('confirmada', 'Confirmada'),
        ('cancelada', 'Cancelada'),
        ('finalizada', 'Finalizada'),
        ('reagendamento_pendente', 'Aguardando Reagendamento'),
    ]
    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default="agendada")
    valor = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    paga = models.BooleanField(default=False)
    observacoes = models.TextField(blank=True, null=True)
    forma_pagamento = models.CharField(max_length=50, blank=True, null=True)
    data_pagamento = models.DateField(blank=True, null=True)
    google_event_id = models.CharField(max_length=255, blank=True, null=True)

    lembrete_whatsapp_enviado = models.BooleanField(default=False)
    reagendamentos_count = models.IntegerField(default=0)

    FORMA_PAGAMENTO_CHOICES = [
        ('', 'Selecione a forma...'),
        ('pix', 'Pix'),
        ('dinheiro', 'Dinheiro'),
        ('cartao_credito', 'Cartão de Crédito'),
        ('cartao_debito', 'Cartão de Debito'),
        ('transferencia', 'Transferência Bancária'),
    ]

    forma_pagamento = models.CharField(
        max_length=50, 
        choices=FORMA_PAGAMENTO_CHOICES, 
        null=True, 
        blank=True
    )    

    data_pagamento = models.DateField(blank=True, null=True)
    google_event_id = models.CharField(max_length=255, blank=True, null=True)
    lembrete_whatsapp_enviado = models.BooleanField(default=False)
    reagendamentos_count = models.IntegerField(default=0)

    class Meta:
        # Índices para acelerar a busca na agenda e dashboards
        indexes = [
            models.Index(fields=['clinic', 'data_hora']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.paciente.nome} - {self.data_hora}"


# -----------------------------
# LOGS DE MENSAGENS
# -----------------------------

class LembreteLog(models.Model):
    consulta = models.ForeignKey(
        Consulta, on_delete=models.CASCADE, related_name='logs_mensagens')
    data_envio = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=50, default="Lembrete 24h")
    status_envio = models.CharField(max_length=20)
    mensagem_corpo = models.TextField()
    resposta_paciente = models.TextField(blank=True, null=True)
    message_id = models.CharField(
        max_length=255, blank=True, null=True, db_index=True)

    class Meta:
        ordering = ['-data_envio']

    def __str__(self):
        return f"Log {self.tipo} - {self.consulta.paciente.nome}"


# -----------------------------
# FINANCEIRO
# -----------------------------

class Financeiro(models.Model):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)
    paciente = models.ForeignKey(
        Paciente, on_delete=models.SET_NULL, null=True, blank=True)
    consulta = models.ForeignKey(
        Consulta, on_delete=models.SET_NULL, null=True, blank=True)
    tipo = models.CharField(max_length=20, choices=(
        ('entrada', 'Entrada'), ('saida', 'Saída')))
    valor = models.DecimalField(max_digits=8, decimal_places=2)
    data = models.DateField()
    descricao = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.tipo} - {self.valor}"


# -----------------------------
# SIGNALS
# -----------------------------

@receiver(post_save, sender=User)
def criar_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=Clinic)
def criar_configuracoes_basicas(sender, instance, created, **kwargs):
    if created:
        Configuracao.objects.get_or_create(clinic=instance)
        # Cria a config de WhatsApp (instancia_nome será definida na view de gerenciar_configuracoes)
        ConfiguracaoWhatsApp.objects.get_or_create(clinic=instance)


def set_clinic(instance):
    """Auxiliar para garantir que todo objeto novo herde a clínica correta."""
    if hasattr(instance, "clinic") and instance.clinic_id:
        return
    if hasattr(instance, "paciente") and instance.paciente:
        instance.clinic = instance.paciente.clinic
    elif hasattr(instance, "user") and hasattr(instance.user, "profile"):
        if instance.user.profile.clinic:
            instance.clinic = instance.user.profile.clinic


@receiver(pre_save, sender=Paciente)
@receiver(pre_save, sender=Consulta)
@receiver(pre_save, sender=Financeiro)
@receiver(pre_save, sender=Dentista)       # Adicionado
@receiver(pre_save, sender=Procedimento)   # Adicionado


def preencher_clinica(sender, instance, **kwargs):
    set_clinic(instance)



# -----------------------------
# AI - GESTÃO DE FIDELIZAÇÃO
# -----------------------------

from django.db import models
from django.conf import settings

class HistoricoFidelizacao(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('contatado', 'Mensagem Enviada'),
        ('nao_respondeu', 'Não Respondeu'),
        ('recusou', 'Recusou / Não quis'),
        ('agendado', 'Agendou Consulta'),
        ('ignorar', 'Não sugerir mais'),
    ]
    
    # ATUALIZADO: Incluindo 'alerta' para o Mix Temporal de 180-365 dias
    CATEGORIA_CHOICES = [
        ('risco', 'Risco'), 
        ('alerta', 'Alerta'), 
        ('retorno', 'Retorno')
    ]

    # Relacionamentos
    clinic = models.ForeignKey('Clinic', on_delete=models.CASCADE)
    paciente = models.ForeignKey('Paciente', on_delete=models.CASCADE)
    
    # Parecer técnico da IA para o dentista (O que foi analisado)
    insight = models.TextField()
    
    # Sugestão de abordagem para o WhatsApp gerada pela IA (O que enviar)
    insight_whatsapp = models.TextField(blank=True, null=True)
    
    # Classificação para as 3 prateleiras do Dashboard
    categoria = models.CharField(
        max_length=20, 
        choices=CATEGORIA_CHOICES, 
        default='retorno'
    )
    
    # Controle de fluxo do Dashboard
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pendente'
    )
    
    # Timestamps
    data_analise = models.DateTimeField(auto_now_add=True)
    ultima_interacao = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-data_analise']
        verbose_name = "Histórico de Fidelização"
        verbose_name_plural = "Históricos de Fidelização"

    def __str__(self):
        return f"{self.paciente.nome} - {self.categoria} ({self.status})"
    



@receiver(post_save, sender=Clinic)
def vincular_dono_ao_profile(sender, instance, created, **kwargs):
    if created:
        profile, _ = Profile.objects.get_or_create(user=instance.dono)
        profile.clinic = instance
        profile.cargo = 'admin'
        profile.save()





# Importe o seu model de Paciente aqui (ajuste o nome se for diferente)
# from .models import Paciente 

class ArquivoPaciente(models.Model):
    # Relaciona com o seu paciente atual
    paciente = models.ForeignKey(
        'Paciente', 
        on_delete=models.CASCADE, 
        related_name='arquivos'
    )
    
    # O arquivo em si (fotos, PDFs, RX)
    arquivo = models.FileField(
        upload_to='pacientes/prontuarios/%Y/%m/',
        verbose_name="Arquivo/Exame"
    )
    
    # Uma descrição curta (ex: "Panorâmica inicial", "Termo de consentimento")
    descricao = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        verbose_name="Descrição"
    )
    
    data_upload = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Arquivo do Paciente"
        verbose_name_plural = "Arquivos dos Pacientes"
        ordering = ['-data_upload']

    def __str__(self):
        return f"Arquivo de {self.paciente.nome} - {self.data_upload.strftime('%d/%m/%Y')}"