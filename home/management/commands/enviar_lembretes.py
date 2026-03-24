import os
import logging
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, datetime, time
from django.db.models import Max
from home.models import Consulta, LembreteLog, ConfiguracaoWhatsApp, Configuracao, Paciente
from home.utils import enviar_mensagem_whatsapp

# Configuração do Logger para monitoramento
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Motor de Disparos OdontoClinics: Lembretes 24h (Fidelização agora é Manual via Dashboard)'

    def handle(self, *args, **kwargs):
        agora_local = timezone.localtime(timezone.now())
        hoje = agora_local.date()

        self.stdout.write(self.style.NOTICE(
            f"--- 🚀 Iniciando Motor de Disparos ({hoje.strftime('%d/%m/%Y')}) ---"))

        # ==========================================================
        # 1. BLOCO: LEMBRETES 24H (CONSULTAS AGENDADAS)
        # ==========================================================
        alvo_lembrete = hoje + \
            timedelta(days=3) if hoje.weekday(
            ) == 4 else hoje + timedelta(days=1)
        inicio_dia = timezone.make_aware(
            datetime.combine(alvo_lembrete, time.min))
        fim_dia = timezone.make_aware(
            datetime.combine(alvo_lembrete, time.max))

        consultas = Consulta.objects.filter(
            data_hora__range=(inicio_dia, fim_dia),
            lembrete_whatsapp_enviado=False,
            status="agendada"
        ).select_related('paciente', 'clinic', 'clinic__whatsapp_config')

        self.stdout.write(self.style.NOTICE(
            f"📅 Lembretes 24h: {consultas.count()} pendentes."))

        for c in consultas:
            self.processar_lembrete_24h(c)

        # ==========================================================
        # 2. BLOCO: FIDELIZAÇÃO (MIGRADO PARA MANUAL)
        # ==========================================================
        self.stdout.write(self.style.WARNING(
            "🔄 Fidelização Automática: Desativada (Processo agora é manual via Dashboard)."))

        self.stdout.write(self.style.SUCCESS(
            "--- ✅ Motor de Disparos Concluído ---"))

    def processar_lembrete_24h(self, c):
        try:
            config_wa = getattr(c.clinic, 'whatsapp_config', None)
            # TRAVA: Só dispara se o switch "Lembretes Ativos" estiver ON e for plano Professional
            if not config_wa or not config_wa.lembretes_ativos or c.clinic.plano != 'professional' or not config_wa.instancia_nome:
                return

            destinatario = self.validar_e_limpar_contato(c.paciente)
            if not destinatario:
                return

            consulta_local = timezone.localtime(c.data_hora)
            config_v = Configuracao.objects.filter(clinic=c.clinic).first()
            nome_prof = config_v.nome_profissional if config_v and config_v.nome_profissional else c.clinic.nome

            try:
                msg = config_wa.mensagem_confirmacao.format(
                    paciente=c.paciente.nome.split()[0],
                    clinica=c.clinic.nome,
                    medico=nome_prof,
                    data=consulta_local.strftime('%d/%m'),
                    hora=consulta_local.strftime('%H:%M')
                )
            except:
                return

            sucesso, res_data = enviar_mensagem_whatsapp(
                config_wa, destinatario, msg, retornar_json=True)
            if sucesso:
                self.atualizar_metadados_e_log(
                    c, res_data, msg, "Lembrete 24h")
                self.stdout.write(self.style.SUCCESS(
                    f"   ✅ 24h: {c.paciente.nome}"))

        except Exception as e:
            logger.error(f"Erro no 24h ({c.id}): {e}")

    def validar_e_limpar_contato(self, paciente):
        """Centraliza a lógica de higienização de JID e Fallback para Telefone"""
        contato = paciente.whatsapp_jid or paciente.telefone_limpo or paciente.telefone

        if not contato or str(contato).strip() in ["None", ""]:
            return None

        if "@g.us" in str(contato):
            paciente.whatsapp_jid = None
            paciente.save(update_fields=['whatsapp_jid'])
            contato = paciente.telefone_limpo or paciente.telefone
            if not contato:
                return None

        return contato

    def atualizar_metadados_e_log(self, consulta, res_data, mensagem, tipo, marcar_enviado=True):
        """Extrai metadados da Evolution e salva o log"""
        try:
            data_content = res_data[0] if isinstance(
                res_data, list) else res_data
            if 'data' in data_content:
                data_content = data_content['data']
                if isinstance(data_content, list):
                    data_content = data_content[0]

            msg_id = data_content.get('key', {}).get(
                'id') or data_content.get('messageId')
            remote_jid = data_content.get('key', {}).get(
                'remoteJid') or data_content.get('jid')

            # Salva o JID real para comunicações futuras (evita problemas @lid)
            if remote_jid and ("@s.whatsapp.net" in remote_jid or "@lid" in remote_jid):
                consulta.paciente.whatsapp_jid = remote_jid
                consulta.paciente.save(update_fields=['whatsapp_jid'])

            if marcar_enviado:
                consulta.lembrete_whatsapp_enviado = True
                consulta.save(update_fields=['lembrete_whatsapp_enviado'])

            LembreteLog.objects.create(
                consulta=consulta,
                status_envio='enviado',
                mensagem_corpo=mensagem,
                tipo=tipo,
                message_id=msg_id
            )
        except Exception as e:
            logger.warning(f"Erro metadados log: {e}")
