import re
from zoneinfo import ZoneInfo

from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from home.models import Profile
from .models import Paciente, Consulta, Financeiro, Configuracao
from .models import Dentista, Procedimento # Import local se necessário




class PacienteForm(forms.ModelForm):
    class Meta:
        model = Paciente
        fields = [
            'nome', 'telefone', 'email', 'cpf', 'data_nascimento',
            'cep', 'endereco', 'numero', 'bairro', 'cidade', 'estado',
            'observacoes_clinicas',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'cpf': forms.TextInput(attrs={'class': 'form-control'}),
            'data_nascimento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'observacoes_clinicas': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'cep': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_cep', 'onblur': 'pesquisacep(this.value);'}),
            'endereco': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_endereco'}),
            'numero': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_numero'}),
            'bairro': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_bairro'}),
            'cidade': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_cidade'}),
            'estado': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_estado'}),
        }

    def __init__(self, *args, **kwargs):
        # Capturamos a clínica passada pela View
        self.clinic = kwargs.pop('clinic', None)
        super(PacienteForm, self).__init__(*args, **kwargs)

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf')
        if not cpf:
            return cpf

        # 1. Limpeza e Validação de Formato
        cpf_limpo = re.sub(r'[^0-9]', '', cpf)
        if len(cpf_limpo) != 11 or cpf_limpo in [c * 11 for c in "0123456789"]:
            raise forms.ValidationError("CPF inválido.")

        # 2. Validação dos Dígitos Verificadores
        soma = sum(int(cpf_limpo[i]) * (10 - i) for i in range(9))
        digito1 = (soma * 10 % 11) % 10
        soma = sum(int(cpf_limpo[i]) * (11 - i) for i in range(10))
        digito2 = (soma * 10 % 11) % 10

        if digito1 != int(cpf_limpo[9]) or digito2 != int(cpf_limpo[10]):
            raise forms.ValidationError("CPF inválido.")

        # Geramos a versão formatada
        cpf_formatado = f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:]}"

        # 3. Verificação de Duplicidade (Blindagem contra dados antigos)
        clinic_validacao = self.clinic or (self.instance.clinic if self.instance.pk else None)

        if clinic_validacao:
            from django.db.models import Q  # Import local para evitar problemas de dependência circular
            
            # Buscamos se existe o CPF formatado OU o CPF limpo no banco
            qs = Paciente.objects.filter(
                clinic=clinic_validacao
            ).filter(
                Q(cpf=cpf_formatado) | Q(cpf=cpf_limpo)
            )
            
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            
            if qs.exists():
                raise forms.ValidationError("Este CPF já está cadastrado nesta clínica.")

        # Retornamos sempre o formatado para "limpar" a database daqui pra frente
        return cpf_formatado

# ---------------------------
# CONSULTA FORM
# ---------------------------

class ConsultaForm(forms.ModelForm):
    FORMA_PAGAMENTO_CHOICES = [
        ('', 'Selecione a forma...'),
        ('pix', 'Pix'),
        ('dinheiro', 'Dinheiro'),
        ('cartao_credito', 'Cartão de Crédito'),
        ('cartao_debito', 'Cartão de Debito'),
        ('transferencia', 'Transferência Bancária'),
    ]

    forma_pagamento = forms.ChoiceField(
        choices=FORMA_PAGAMENTO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Consulta
        fields = [
            'paciente', 'dentista', 'procedimento', 'responsavel', 'data_hora', 'status',
            'valor', 'paga', 'forma_pagamento', 'data_pagamento', 'observacoes'
        ]
        widgets = {
            'paciente': forms.Select(attrs={'class': 'form-select select2', 'data-placeholder': 'Selecione o paciente'}),
            'dentista': forms.Select(attrs={'class': 'form-select select2', 'data-placeholder': 'Selecione o dentista'}),
            'procedimento': forms.Select(attrs={'class': 'form-select select2', 'data-placeholder': 'Selecione o procedimento'}),
            'responsavel': forms.Select(attrs={'class': 'form-select select2', 'data-placeholder': 'Selecione o responsável (opcional)'}),
            'data_hora': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M'
            ),
            'data_pagamento': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'},
                format='%Y-%m-%d'
            ),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'paga': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        clinic = kwargs.pop('clinic', None)
        super().__init__(*args, **kwargs)

        # Garante que o Django aceite o formato vindo do input datetime-local do navegador
        self.fields['data_hora'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S']

        # 1. Filtro de Clínica
        if clinic:
            queryset = Paciente.objects.filter(clinic=clinic).order_by('nome')
            self.fields['paciente'].queryset = queryset
            if 'responsavel' in self.fields and hasattr(self.fields['responsavel'], 'queryset'):
                self.fields['responsavel'].queryset = queryset
            self.fields['dentista'].queryset = Dentista.objects.filter(clinic=clinic, ativo=True).order_by('nome')
            self.fields['procedimento'].queryset = Procedimento.objects.filter(clinic=clinic, ativo=True).order_by('nome')

        # 2. Configurações para Select2
        self.fields['paciente'].empty_label = "Selecione o Paciente"
        self.fields['dentista'].empty_label = "Selecione o Dentista"
        self.fields['procedimento'].empty_label = "Selecione o Procedimento"
        if 'responsavel' in self.fields:
            self.fields['responsavel'].empty_label = "Selecione o Responsável (Opcional)"

        # 3. Formatação de Datas para edição (Preenchimento do form)
        if self.instance and self.instance.pk:
            if self.instance.data_hora:
                # Converte para o fuso local (São Paulo) antes de formatar para o input HTML
                local_dt = timezone.localtime(self.instance.data_hora)
                self.initial['data_hora'] = local_dt.strftime('%Y-%m-%dT%H:%M')
            
            if hasattr(self.instance, 'data_pagamento') and self.instance.data_pagamento:
                self.initial['data_pagamento'] = self.instance.data_pagamento.strftime('%Y-%m-%d')

        # 4. Campos Opcionais
        optional_fields = ['responsavel', 'valor', 'paga', 'data_pagamento', 'forma_pagamento']
        for field in optional_fields:
            if field in self.fields:
                self.fields[field].required = False

    def clean_data_hora(self):
        data_hora = self.cleaned_data.get('data_hora')
        if data_hora:
            # 1. Pegamos o horário "cru" (sem fuso)
            # Se o navegador enviou 09:00, o 'naive' será 09:00
            naive_dt = data_hora.replace(tzinfo=None)
            
            # 2. Forçamos o fuso de São Paulo sobre esse valor
            return timezone.make_aware(naive_dt, ZoneInfo('America/Sao_Paulo'))
        return data_hora
    



    
# ---------------------------
# FINANCEIRO
# ---------------------------


class FinanceiroForm(forms.ModelForm):
    class Meta:
        model = Financeiro
        fields = ['tipo', 'valor', 'data', 'descricao']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control'}),
            'data': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'descricao': forms.TextInput(attrs={'class': 'form-control'}),
        }


# ---------------------------
# CONFIGURAÇÃO (ÚNICA)
# ---------------------------

class ConfiguracaoForm(forms.ModelForm):
    class Meta:
        model = Configuracao
        fields = [
            'nome_clinica',
            'nome_profissional',
            'cro',
            'documento_fiscal',
            'email',
            'telefone',
            'endereco',
            'logo',
            'assinatura_digital',
        ]
        widgets = {
            'nome_clinica': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome da Clínica'}),
            'nome_profissional': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome do Dentista Responsável'}),
            'cro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: CRO-SP 123456'}),
            'documento_fiscal': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CPF ou CNPJ'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'contato@clinica.com'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '(00) 00000-0000'}),
            'endereco': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Rua, número, bairro, cidade - UF'}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'assinatura_digital': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


# ---------------------------
# USUÁRIOS (ADMIN)
# ---------------------------


class UsuarioForm(forms.ModelForm):
    cargo = forms.ChoiceField(
        choices=Profile.CARGOS,  # usa os choices do model Profile
        label="Cargo",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    ativo = forms.BooleanField(
        required=False,
        initial=True,
        label="Usuário ativo"
    )

    password1 = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=True
    )
    password2 = forms.CharField(
        label="Confirme a senha",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=True
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def clean(self):
        # O clean garante que os dados submetidos sejam validados
        cleaned_data = super().clean()
        return cleaned_data

    def save(self, commit=True):
        # 1. Cria a instância na memória (ainda não salvou no banco)
        instance = super().save(commit=False)

        # 2. Pega os valores reais que vieram do formulário
        paga = self.cleaned_data.get('paga')
        # Usamos instance.status para garantir que estamos olhando para o dado do objeto

        # 3. A LÓGICA FORÇADA:
        # Se 'paga' for True (marcado) e o status for um dos pendentes
        if paga and instance.status in ['agendada', 'confirmada']:
            instance.status = 'finalizada'

        # 4. Salva no banco de dados
        if commit:
            instance.save()
            # Se o seu formulário tem campos ManyToMany (como tags ou Select2 múltiplos),
            # é boa prática chamar save_m2m()
            self.save_m2m()

        return instance
