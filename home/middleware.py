from django.shortcuts import redirect
from .models import Configuracao, Profile

class ClinicaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.clinic = None
        request.config = None

        if request.user.is_authenticated:
            # 1. Tentamos pegar a clínica direto pelo User (mais rápido devido ao OneToOneField)
            # Usamos o related_name 'minha_clinica' que você definiu no Model Clinic
            clinica = getattr(request.user, 'minha_clinica', None)
            
            if clinica:
                request.clinic = clinica
                # 2. Pegamos a configuração visual
                request.config = Configuracao.objects.filter(clinic=clinica).first()

                # 3. LÓGICA DE BLOQUEIO (Expiração do Trial)
                # Verifica se os dias acabaram e se o plano não é Professional
                if clinica.dias_restantes <= 0 and clinica.plano != 'professional' and not request.user.is_superuser:
                    
                    # Nomes das URLs que NÃO devem ser bloqueadas
                    allowed_url_names = ['planos', 'logout', 'admin:index']
                    
                    # Resolve o nome da URL atual
                    current_url_name = request.resolver_match.url_name if request.resolver_match else None
                    
                    if current_url_name not in allowed_url_names:
                        return redirect('planos')
            else:
                # Caso o usuário não tenha clínica vinculada diretamente, 
                # podemos tentar via Profile (se for um funcionário, por exemplo)
                try:
                    perfil = Profile.objects.select_related('clinic').get(user=request.user)
                    if perfil.clinic:
                        request.clinic = perfil.clinic
                        request.config = Configuracao.objects.filter(clinic=perfil.clinic).first()
                except Profile.DoesNotExist:
                    pass

        return self.get_response(request)