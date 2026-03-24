from django.utils import timezone
from .models import Configuracao

def clinica_context(request):
    """
    Context Processor unificado para gerenciar Configurações e Status de Teste.
    """
    context = {
        'config': None,
        'dias_restantes': 0,
        'is_trial': False,
        'clinica': None
    }

    if request.user.is_authenticated:
        # Usando o related_name 'minha_clinica' que você definiu no OneToOneField do Model
        clinica = getattr(request.user, 'minha_clinica', None)

        if clinica:
            context['clinica'] = clinica
            # 1. Busca a configuração visual (Logo, Cores, etc)
            context['config'] = Configuracao.objects.filter(clinic=clinica).first()
            
            # 2. Lógica do Contador (Usando a property que criamos no Model)
            context['dias_restantes'] = clinica.dias_restantes
            
            # 3. Exibe o aviso apenas se a property do Model permitir
            # (Lembra? Se for Professional ou se os dias acabarem, ela retorna False)
            context['is_trial'] = clinica.exibir_aviso_teste

    return context