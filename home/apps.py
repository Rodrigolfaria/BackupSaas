from django.apps import AppConfig


class HomeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'home'
    verbose_name = 'Módulo Principal'

    def ready(self):
        """
        Método executado quando o Django inicializa o app.
        As signals foram movidas para models.py, então não há
        necessidade de importações adicionais aqui.
        """
        pass
