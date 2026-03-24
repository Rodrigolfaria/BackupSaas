from home.models import Paciente
from django.utils import timezone

for p in Paciente.objects.all():
    if timezone.is_naive(p.data_cadastro):
        p.data_cadastro = timezone.make_aware(p.data_cadastro)
        p.save()

print("Corrigido com sucesso!")
