import os
import django

# Setup do Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'seu_projeto.settings') # Ajuste o nome do seu projeto aqui
django.setup()

from home.models import Paciente

def popular():
    pacientes = Paciente.objects.filter(telefone_limpo__isnull=True) | Paciente.objects.filter(telefone_limpo='')
    print(f"Atualizando {pacientes.count()} pacientes...")
    
    for p in pacientes:
        # O método save() que editamos antes já vai limpar o telefone automaticamente
        p.save() 
        
    print("Concluído!")

if __name__ == '__main__':
    popular()