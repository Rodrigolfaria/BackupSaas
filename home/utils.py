import requests
import json
import logging
import os
import re
from datetime import timedelta
from django.conf import settings
from django.utils import timezone

# Configuração do Logger
logger = logging.getLogger(__name__)

# --- 1. GOOGLE CALENDAR (LÓGICA UNIFICADA COM REQUESTS) ---


def google_refresh_token(profile):
    """Renova o access_token usando o refresh_token do Profile."""
    if not profile.google_refresh_token:
        logger.error(f"❌ Refresh Token ausente para o perfil: {profile.id}")
        return None

    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": profile.google_refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        response = requests.post(url, data=data).json()
        new_token = response.get("access_token")
        expires_in = response.get("expires_in")

        if new_token:
            profile.google_access_token = new_token
            # Atualiza expiração (UTC)
            profile.google_token_expiry = timezone.now() + timedelta(seconds=expires_in)
            profile.save()
            return new_token
    except Exception as e:
        logger.error(f"🚨 Erro ao renovar token Google: {str(e)}")
    return None


def google_get_token(profile):
    """Retorna um access_token válido, renovando se estiver expirado."""
    if not profile.google_access_token:
        return None

    # Se expira em menos de 1 minuto, renova
    agora = timezone.now()
    if profile.google_token_expiry and profile.google_token_expiry < (agora + timedelta(minutes=1)):
        return google_refresh_token(profile)

    return profile.google_access_token

def google_create_event(profile, consulta, data_fim=None):
    """
    Atalho para google_update_event para manter compatibilidade com as views.
    Aceita data_fim opcional.
    """
    # Se a view passou uma data_fim específica, podemos usar aqui.
    # Caso contrário, a google_update_event já calcula 30 minutos por padrão.
    return google_update_event(profile, consulta, data_fim_manual=data_fim)

def google_update_event(profile, consulta, data_fim_manual=None):
    """
    Cria ou Atualiza evento no Google Calendar via REST API (Requests).
    Duração: 30 minutos (padrão) ou data_fim_manual.
    """
    token = google_get_token(profile)
    if not token:
        return None

    event_id = consulta.google_event_id
    base_url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

    if event_id:
        url = f"{base_url}/{event_id}"
        method = requests.put
    else:
        url = base_url
        method = requests.post

    # LÓGICA DE HORÁRIO AJUSTADA:
    data_inicio = timezone.localtime(consulta.data_hora)
    
    # Se a view passou uma data_fim (30min), usamos ela. Se não, calculamos 30min aqui.
    if data_fim_manual:
        data_fim = timezone.localtime(data_fim_manual)
    else:
        data_fim = data_inicio + timedelta(minutes=30)

    payload = {
        "summary": f"👤 {consulta.paciente.nome}",
        "description": f"Status: {consulta.status}\nResponsável: {consulta.responsavel or 'Clínica'}\nObs: {consulta.observacoes or ''}",
        "start": {"dateTime": data_inicio.isoformat()},
        "end": {"dateTime": data_fim.isoformat()},
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # ... (resto do seu código de requests.method atual permanece igual)
    try:
        response = method(url, json=payload, headers=headers)
        res_data = response.json()
        if response.status_code in [200, 201]:
            if not event_id:
                consulta.google_event_id = res_data.get("id")
                consulta.save()
            logger.info(f"✅ Sincronismo Google OK: {consulta.paciente.nome}")
            return res_data.get("id")
        else:
            logger.error(f"❌ Erro API Google ({response.status_code}): {response.text}")
            return None
    except Exception as e:
        logger.error(f"🚨 Erro crítico google_update_event: {str(e)}")
        return None


# --- 2. WHATSAPP / EVOLUTION API ---

def enviar_mensagem_whatsapp(config, jid_ou_numero, texto, jid_alternativo=None, retornar_json=False):
    """
    Função universal para envio de mensagens via Evolution API.
    """
    base_url = os.getenv("EVOLUTION_API_URL_BASE",
                         "https://api-clinica-whatsapp.onrender.com")
    api_key = config.apikey_instancia or os.getenv(
        "EVOLUTION_API_KEY", "793668e6117cb452845e0ea2b60a3f1f")

    if not config.instancia_nome:
        logger.error(
            f"Instância não configurada para a clínica: {config.clinic.nome}")
        return False, None

    url = f"{base_url}/message/sendText/{config.instancia_nome}"
    headers = {"Content-Type": "application/json", "apikey": api_key}

    destinatario = str(jid_ou_numero).strip()
    if "@" not in destinatario:
        digitos = re.sub(r'\D', '', destinatario)
        if len(digitos) <= 11 and not digitos.startswith("55") and digitos != "":
            digitos = f"55{digitos}"
        destinatario = f"{digitos}@s.whatsapp.net"

    payload = {
        "number": destinatario,
        "text": texto,
        "delay": 1200,
        "linkPreview": True
    }

    try:
        logger.info(f"📡 Enviando WhatsApp para {destinatario}...")
        response = requests.post(
            url, json=payload, headers=headers, timeout=20)

        try:
            res_data = response.json()
        except ValueError:
            res_data = {"error": "Resposta inválida", "text": response.text}

        sucesso = response.status_code in [200, 201]

        if retornar_json:
            return sucesso, res_data

        if sucesso:
            message_id = (res_data.get('key', {}).get('id') or
                          res_data.get('messageId') or
                          res_data.get('item', [{}])[0].get('key', {}).get('id'))
            return True, message_id

        if jid_alternativo and jid_alternativo != jid_ou_numero:
            return enviar_mensagem_whatsapp(config, jid_alternativo, texto, retornar_json=retornar_json)

        return False, None

    except Exception as e:
        logger.error(f"🚨 Erro de conexão WhatsApp: {str(e)}")
        return False, None


def google_delete_event(profile, consulta):
    """Remove o evento do Google Calendar."""
    if not consulta.google_event_id:
        return

    token = google_get_token(profile)
    if not token:
        return

    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{consulta.google_event_id}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.delete(url, headers=headers, timeout=10)
        # 204=Sucesso, 404=Já não existia lá
        if response.status_code in [204, 404]:
            logger.info(
                f"✅ Evento Google removido: {consulta.google_event_id}")
        else:
            logger.warning(
                f"⚠️ Google retornou status {response.status_code} na exclusão.")
    except Exception as e:
        logger.error(f"🚨 Falha na conexão ao deletar evento: {str(e)}")
