import openai
from django.conf import settings
import os
import json
import logging
import traceback
import re

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.is_local = getattr(settings, 'DEBUG', True)
        api_key = os.getenv("GROQ_API_KEY") or getattr(settings, 'GROQ_API_KEY', None)
        self.client = openai.OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key
        )
        self.model_complex = "llama-3.3-70b-versatile"
        self.model_fast = "llama-3.1-8b-instant"

    def _limpar_json(self, texto):
        try:
            texto = texto.replace("```json", "").replace("```", "").strip()
            match = re.search(r'(\{.*\}|\[.*\])', texto, re.DOTALL)
            if match:
                return match.group(1)
            return texto
        except Exception as e:
            logger.error(f"Erro ao limpar JSON da IA: {e}")
            return texto

    def analisar_estrategias_fidelizacao(self, lista_pacientes):
        """
        Analisa o Mix Temporal e gera pareceres técnicos segmentados.
        """
        print(f"IA processando {len(lista_pacientes)} pacientes (Mix Temporal) com Llama 3.3 70B...")

        system_instruction = (
            "Você é o Diretor Clínico da OdontoClinics. Sua análise é técnica e estratégica.\n"
            "O payload contém pacientes divididos por tempo de ausência. Respeite as seguintes diretrizes:\n\n"
            
            "1. REATIVAÇÃO CRÍTICA (>365 dias): Foco em 'Abandono de Tratamento'. Cite riscos de perda óssea, "
            "movimentação indesejada ou falha em próteses antigas.\n"
            
            "2. PREVENÇÃO EM ATRASO (180-365 dias): Foco em 'Manutenção Preventiva'. Cite calcificação de biofilme, "
            "perda do polimento coronário ou progressão de cáries incipientes.\n"
            
            "3. ALERTA PRECOCE (90-180 dias): Foco em 'Continuidade'. Cite acompanhamento biomecânico e "
            "estabilidade dos tecidos moles.\n\n"
            
            "REGRAS DE OUTPUT:\n"
            "- Retorne um JSON com três listas: 'critico', 'alerta' e 'retorno'.\n"
            "- Cada objeto DEVE conter: 'id' e 'reasoning'.\n"
            "- O campo 'reasoning' deve ter 2 a 3 frases técnicas: [Diagnóstico Baseado no Tempo] -> [Risco Clínico].\n"
            "- REGRA ABSOLUTA: Processe TODOS os IDs enviados no JSON."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model_complex,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": json.dumps(lista_pacientes)}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            dados = json.loads(self._limpar_json(content))

            # Mapeamos as novas chaves para garantir consistência
            return {
                "critico": dados.get("critico", []),
                "alerta": dados.get("alerta", []),
                "retorno": dados.get("retorno", [])
            }

        except Exception as e:
            logger.error(f"Erro no 70B: {e}")
            return self._fallback_analise_8b(lista_pacientes, system_instruction)

    def _fallback_analise_8b(self, lista_pacientes, instruction):
        try:
            response = self.client.chat.completions.create(
                model=self.model_fast,
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": json.dumps(lista_pacientes)}
                ],
                temperature=0.1
            )
            content = response.choices[0].message.content
            dados = json.loads(self._limpar_json(content))
            return {
                "critico": dados.get("critico", []),
                "alerta": dados.get("alerta", []),
                "retorno": dados.get("retorno", [])
            }
        except Exception:
            return {"critico": [], "alerta": [], "retorno": []}

    def gerar_insight_fidelizacao(self, nome_paciente, dias_ausente, historico="", reasoning=""):
        """
        Gera abordagem de WhatsApp SEM menção a tempo.
        """
        primeiro_nome = nome_paciente.split()[0] if nome_paciente else "Paciente"

        system_instruction = (
            "Você é o concierge da OdontoClinics. Transforme o parecer técnico em uma mensagem de cuidado.\n"
            "DIRETRIZES DE WHATSAPP:\n"
            "- PROIBIDO: Mencionar dias, meses ou anos (ex: 'faz tempo que não te vemos').\n"
            "- FOCO: Use a justificativa técnica para convidar para uma avaliação (ex: 'revisar o ajuste da sua prótese').\n"
            "- TOM: Profissional, acolhedor e focado em saúde.\n"
            "- Máximo 300 caracteres."
        )

        user_content = f"PACIENTE: {primeiro_nome} | PARECER TÉCNICO: {reasoning}"

        try:
            response = self.client.chat.completions.create(
                model=self.model_fast,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return f"Olá {primeiro_nome}! Gostaria de agendar uma consulta de revisão para acompanharmos sua saúde bucal?"