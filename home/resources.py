import re
import decimal
from datetime import datetime, date
from django.utils import timezone
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, DateWidget, DecimalWidget
from import_export.widgets import DateTimeWidget

# Importando os modelos
from .models import Paciente, Clinic, Consulta, Financeiro

# --- FUNÇÃO AUXILIAR DE TIMEZONE ---


def tornar_aware(valor):
    """
    Converte date para datetime se necessário e torna o objeto ciente do fuso horário (aware).
    Isso evita o erro 'datetime.date object has no attribute utcoffset'.
    """
    if valor is None:
        return None

    # Se for apenas data (date), transforma em datetime (meia-noite)
    if isinstance(valor, date) and not isinstance(valor, datetime):
        valor = datetime.combine(valor, datetime.min.time())

    # Se for datetime e não tiver fuso horário, aplica o do Django
    if isinstance(valor, datetime) and timezone.is_naive(valor):
        return timezone.make_aware(valor)

    return valor

# --- 1. WIDGETS DE TRATAMENTO ---


class DecimalLimpoWidget(DecimalWidget):
    """Limpa 'R$ 150,00' para Decimal('150.00')"""

    def clean(self, value, row=None, *args, **kwargs):
        if value is None or str(value).strip() == "":
            return decimal.Decimal('0.00')
        val_str = str(value).replace('R$', '').replace(
            ' ', '').replace('.', '').replace(',', '.').strip()
        try:
            return decimal.Decimal(val_str)
        except:
            return decimal.Decimal('0.00')


class PacienteBuscaOuCriaWidget(ForeignKeyWidget):
    """Busca por CPF ou Nome antes de criar para evitar duplicados"""

    def clean(self, value, row=None, *args, **kwargs):
        if not value:
            return None

        nome_input = str(value).strip().title()
        cpf_raw = row.get('CPF') or row.get('cpf')
        cpf_limpo = re.sub(r'\D', '', str(cpf_raw)) if cpf_raw else None

        clinic_id = getattr(self, 'clinic_id', None)
        if not clinic_id:
            primeira = Clinic.objects.first()
            clinic_id = primeira.id if primeira else None

        paciente = None
        if cpf_limpo:
            paciente = Paciente.objects.filter(
                cpf=cpf_limpo, clinic_id=clinic_id).first()

        if not paciente:
            paciente = Paciente.objects.filter(
                nome__iexact=nome_input, clinic_id=clinic_id).first()

        if not paciente:
            # CORREÇÃO: Usando timezone.now() para evitar Naive DateTime Warning
            paciente = Paciente.objects.create(
                nome=nome_input,
                clinic_id=clinic_id,
                cpf=cpf_limpo,
                data_cadastro=timezone.now()
            )
        return paciente

# --- 2. RESOURCE DE PACIENTE ---


class PacienteResource(resources.ModelResource):
    nome = fields.Field(attribute='nome', column_name='NOME DO PACIENTE')
    telefone = fields.Field(attribute='telefone', column_name='CELULAR')
    cpf = fields.Field(attribute='cpf', column_name='CPF')
    data_nascimento = fields.Field(
        attribute='data_nascimento', column_name='DATA NASCIMENTO', widget=DateWidget(format='%d/%m/%Y'))
    data_cadastro = fields.Field(
        attribute='data_cadastro', column_name='DATA DE CADASTRO', widget=DateWidget(format='%d/%m/%Y'))
    clinic = fields.Field(attribute='clinic', column_name='clinic',
                          widget=ForeignKeyWidget(Clinic, 'id'))

    class Meta:
        model = Paciente
        import_id_fields = ('cpf', 'clinic')
        fields = ('nome', 'telefone', 'data_nascimento', 'data_cadastro',
                  'cpf', 'endereco', 'numero', 'bairro', 'cidade', 'estado', 'clinic')
        skip_unchanged = True

    def __init__(self, *args, **kwargs):
        self.clinic_id = kwargs.pop('clinic_id', None)
        super().__init__(*args, **kwargs)

    def before_import_row(self, row, **kwargs):
        if self.clinic_id:
            row['clinic'] = self.clinic_id

        if row.get('CPF'):
            row['CPF'] = re.sub(r'\D', '', str(row.get('CPF')))[:11]
        if row.get('CELULAR'):
            row['CELULAR'] = re.sub(r'\D', '', str(row.get('CELULAR')))[:11]
        if row.get('UF'):
            row['UF'] = str(row.get('UF')).strip().upper()[:2]
        if row.get('NOME DO PACIENTE'):
            row['NOME DO PACIENTE'] = str(
                row.get('NOME DO PACIENTE')).strip().title()

    def before_save_instance(self, instance, row, **kwargs):
        # CORREÇÃO: Garante que a data de cadastro vinda do arquivo seja aware
        if instance.data_cadastro:
            instance.data_cadastro = tornar_aware(instance.data_cadastro)

# --- 3. RESOURCE DE CONSULTA ---


class ConsultaResource(resources.ModelResource):
    # 1. Mapeamento de Campos com Widgets Customizados
    data = fields.Field(
        attribute='data_hora', 
        column_name='DATA',
        widget=DateTimeWidget(format='%d/%m/%Y %H:%M')
    )

    paciente = fields.Field(
        attribute='paciente', 
        column_name='NOME DO PACIENTE',
        widget=PacienteBuscaOuCriaWidget(Paciente, 'nome')
    )

    # Corrigido: Agora o responsável também usa o widget de busca/criação
    responsavel = fields.Field(
        attribute='responsavel', 
        column_name='NOME DO RESPONSAVEL',
        widget=PacienteBuscaOuCriaWidget(Paciente, 'nome')
    )

    valor = fields.Field(
        attribute='valor', 
        column_name='VALOR', 
        widget=DecimalLimpoWidget()
    )

    observacoes = fields.Field(
        attribute='observacoes', 
        column_name='OBSERVACOES'
    )

    forma_pagamento = fields.Field(
        attribute='forma_pagamento', 
        column_name='FORMA DE PAGAMENTO'
    )

    class Meta:
        model = Consulta
        # Importante: Vazio para sempre criar novos registros ao importar
        import_id_fields = []
        raise_errors = True
        report_skipped = True
        fields = ('data', 'paciente', 'responsavel', 'valor', 'forma_pagamento', 'observacoes')
        skip_unchanged = False

    def __init__(self, *args, **kwargs):
        # Captura a clínica injetada pela View
        self.clinic_id = kwargs.pop('clinic_id', None)
        super().__init__(*args, **kwargs)
        
        # Injeta a clinic_id nos widgets de busca para garantir o isolamento (Multi-tenant)
        if self.clinic_id:
            self.fields['paciente'].widget.clinic_id = self.clinic_id
            self.fields['responsavel'].widget.clinic_id = self.clinic_id

    def before_import_row(self, row, **kwargs):
        # Disponibiliza a clínica na linha para uso dos widgets durante a limpeza
        if self.clinic_id:
            row['clinic'] = self.clinic_id

    def before_save_instance(self, instance, row, **kwargs):
        # 1. VÍNCULO DE SEGURANÇA DA CLÍNICA (O MAIS IMPORTANTE)
        # Forçamos o ID da clínica que foi passado no __init__ do Resource
        if self.clinic_id:
            instance.clinic_id = self.clinic_id
            # Opcional: print para conferir no terminal do VS Code durante o teste
            # print(f"DEBUG: Importando para Clínica ID {self.clinic_id}")
        else:
            # Se não houver clinic_id, interrompemos a operação por segurança
            raise ValueError("Erro de Segurança: Nenhuma clínica identificada para a importação.")

        # 2. Tratamento de Timezone (Garante compatibilidade com o banco)
        if instance.data_hora:
            instance.data_hora = tornar_aware(instance.data_hora)

        # 3. Regras de Negócio Automáticas
        instance.status = 'confirmada'
        instance.paga = True

        # 4. Sincronização de Datas
        if instance.data_hora:
            # Se instance.data_hora for DateTime, pegamos apenas a parte da Date
            instance.data_pagamento = instance.data_hora.date()
        else:
            instance.data_pagamento = timezone.localdate()

        # O campo responsavel e paciente já foram tratados pelos Widgets, 
        # mas garantimos que a clínica deles seja a mesma da consulta
        if instance.paciente:
            instance.paciente.clinic_id = self.clinic_id
        if instance.responsavel:
            instance.responsavel.clinic_id = self.clinic_id

    def after_save_instance(self, instance, *args, **kwargs):
        """ GERA O FINANCEIRO """
        dry_run = kwargs.get('dry_run', False)

        if not dry_run and instance.id and instance.valor > 0:
            Financeiro.objects.update_or_create(
                consulta=instance,
                defaults={
                    'clinic': instance.clinic,
                    'paciente': instance.paciente,
                    'tipo': 'entrada',
                    'valor': instance.valor,
                    'data': instance.data_pagamento,
                    'descricao': f"Importado: {instance.paciente.nome}",
                }
            )
