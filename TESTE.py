import streamlit as st
import pandas as pd
import datetime
import pytz
from supabase import create_client
import base64
from pathlib import Path
from dotenv import load_dotenv
import os
import pytz

# Definir fuso horário de São Paulo
TZ = pytz.timezone("America/Sao_Paulo")


# =============================
# Login centralizado e estilizado
# =============================
usuarios = {
    "admin": "admin",
    "Maria": "maria",
    "Catia": "catia",
    "Vera": "vera",
    "Bruno": "bruno"
}

def login():
    if 'logado' not in st.session_state:
        st.session_state['logado'] = False
        st.session_state['usuario'] = None

    if not st.session_state['logado']:
        # Tela centralizada
        st.markdown("""
        <div style="
            max-width:400px;
            margin:auto;
            margin-top:100px;
            padding:40px;
            border-radius:15px;
            background: linear-gradient(135deg, #DDE3FF, #E5F5E5);
            box-shadow: 0px 0px 20px rgba(0,0,0,0.1);
            text-align:center;
        ">
            <h1 style='color:#2F4F4F;'>🔒 MÓDULO DE PRODUÇÃO</h1>
            <p style='color:#555;'>Entre com seu usuário e senha</p>
        </div>
        """, unsafe_allow_html=True)

        usuario = st.text_input("Usuário", key="login_user")
        senha = st.text_input("Senha", type="password", key="login_pass")

        if st.button("Entrar"):
            if usuario in usuarios and usuarios[usuario] == senha:
                st.session_state['logado'] = True
                st.session_state['usuario'] = usuario
                st.success(f"✅ Bem-vindo, {usuario}!")
                st.experimental_rerun()  # força atualização para carregar conteúdo
            else:
                st.error("❌ Usuário ou senha incorretos.")
        st.stop()
    else:
        st.sidebar.write(f"👤 Logado como: `{st.session_state['usuario']}`")
        if st.sidebar.button("Sair"):
            st.session_state['logado'] = False
            st.session_state['usuario'] = None
            st.experimental_rerun()

# Carregar variáveis de ambiente
env_path = Path(__file__).parent / "teste.env"
load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔐 Executa login antes de mostrar o app
login()


# ==============================
# Funções de Supabase
# ==============================
def carregar_checklists():
    data_total = []
    inicio = 0
    passo = 1000

    while True:
        response = supabase.table("checklists").select("*").range(inicio, inicio + passo - 1).execute()
        dados = response.data
        if not dados:
            break
        data_total.extend(dados)
        inicio += passo

    df = pd.DataFrame(data_total)
    if not df.empty and "data_hora" in df.columns:
        df["data_hora"] = pd.to_datetime(df["data_hora"], utc=True).dt.tz_convert(TZ)
    return df

def salvar_checklist(serie, resultados, usuario, reinspecao=False):
    # Determina se o produto foi reprovado
    reprovado = any(info['status'] == "Não Conforme" for info in resultados.values())

    data_hora_utc = datetime.datetime.now(TZ).astimezone(pytz.UTC).isoformat()

    for item, info in resultados.items():
        payload = {
            "numero_serie": serie,
            "item": item,
            "status": info.get('status', ''),
            "observacoes": info.get('obs', ''),
            "inspetor": usuario,
            "data_hora": data_hora_utc,
            "produto_reprovado": "Sim" if reprovado else "Não",
            "reinspecao": "Sim" if reinspecao else "Não"
        }
        try:
            supabase.table("checklists").insert(payload).execute()
        except Exception as e:
            st.error(f"❌ Erro ao salvar no banco de dados: {e}")
            raise

    st.success(f"✅ Checklist salvo com sucesso para o Nº de Série {serie}")
    return True

def carregar_apontamentos():
    response = supabase.table("apontamentos").select("*").limit(1000).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["data_hora"] = pd.to_datetime(df["data_hora"], utc=True, format="ISO8601").dt.tz_convert(TZ)
    return df

# ==============================
# Funções de Checklist
# ==============================
def status_emoji_para_texto(emoji):
    return {"✅": "Conforme", "❌": "Não Conforme", "🟡": "N/A"}.get(emoji, "N/A")

def checklist_qualidade(numero_serie, usuario):
    st.markdown(f"## ✔️ Checklist de Qualidade – Nº de Série: {numero_serie}")

    if "checklist_bloqueado" not in st.session_state:
        st.session_state.checklist_bloqueado = False

    perguntas = [
        "Etiqueta do produto – As informações estão corretas / legíveis conforme modelo e gravação do eixo?",
        "Placa do Inmetro está correta / fixada e legível? Número corresponde à viga? Gravação do número de série da viga está legível e pintada?",
        "Etiqueta do ABS está conforme? Com número de série compatível ao da viga? Teste do ABS está aprovado?",
        "Rodagem – tipo correto? Especifique o modelo",
        "Graxeiras e Anéis elásticos estão em perfeito estado?",
        "Sistema de atuação correto? Springs ou cuícas em perfeitas condições? Especifique o modelo:",
        "Catraca do freio correta? Especifique modelo",
        "Tampa do cubo correta, livre de avarias e pintura nos critérios? As tampas dos cubos dos ambos os lados são iguais?",
        "Pintura do eixo livre de oxidação, isento de escorrimento na pintura, pontos sem tinta e camada conforme padrão?",
        "Os cordões de solda do eixo estão conformes?"
    ]

    item_keys = {
        1: "ETIQUETA",
        2: "PLACA_IMETRO E NÚMERO DE SÉRIE",
        3: "TESTE_ABS",
        4: "RODAGEM_MODELO",
        5: "GRAXEIRAS E ANÉIS ELÁSTICOS",
        6: "SISTEMA_ATUACAO",
        7: "CATRACA_FREIO",
        8: "TAMPA_CUBO",
        9: "PINTURA_EIXO",
        10: "SOLDA"
    }

    opcoes_modelos = {
        4: ["Single", "Aço", "Alumínio", "N/A"],
        6: ["Spring", "Cuíca", "N/A"],
        7: ["Automático", "Manual", "N/A"],
        10: ["Conforme", "Respingo", "Falta de cordão", "Porosidade", "Falta de Fusão"]
    }

    resultados = {}
    modelos = {}

    st.write("Clique no botão correspondente a cada item:")
    st.caption("✅ = Conforme | ❌ = Não Conforme | 🟡 = N/A")

    with st.form(key=f"form_checklist_{numero_serie}", clear_on_submit=False):
        for i, pergunta in enumerate(perguntas, start=1):
            cols = st.columns([7, 2, 2])
            cols[0].markdown(f"**{i}. {pergunta}**")

            escolha = cols[1].radio(
                "",
                ["✅", "❌", "🟡"],
                key=f"resp_{numero_serie}_{i}",
                horizontal=True,
                label_visibility="collapsed",
                index=None
            )
            resultados[i] = escolha

            if i in opcoes_modelos:
                modelo = cols[2].selectbox(
                    "Modelo",
                    [""] + opcoes_modelos[i],
                    key=f"modelo_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )
                modelos[i] = modelo
            else:
                modelos[i] = None

        submit = st.form_submit_button("💾 Salvar Checklist")

    if submit:
        if st.session_state.checklist_bloqueado:
            st.warning("⏳ Salvamento em andamento... aguarde.")
            return
        st.session_state.checklist_bloqueado = True

        faltando = [i for i, resp in resultados.items() if resp is None]
        modelos_faltando = [i for i in opcoes_modelos if modelos.get(i) is None or modelos[i] == ""]
        if faltando or modelos_faltando:
            msg = ""
            if faltando:
                msg += f"⚠️ Responda todas as perguntas! Faltam: {[item_keys[i] for i in faltando]}\n"
            if modelos_faltando:
                msg += f"⚠️ Preencha todos os modelos! Faltam: {[item_keys[i] for i in modelos_faltando]}"
            st.error(msg)
            st.session_state.checklist_bloqueado = False
            return

        dados_para_salvar = {}
        for i, resp in resultados.items():
            chave_item = item_keys.get(i, f"Item_{i}")
            dados_para_salvar[chave_item] = {
                "status": status_emoji_para_texto(resp),
                "obs": modelos.get(i)
            }

        salvar_checklist(numero_serie, dados_para_salvar, usuario)
        st.session_state.checklist_bloqueado = False

# ==============================
# Reinspeção
# ==============================
def checklist_reinspecao(numero_serie, usuario):
    st.markdown(f"## 🔄 Reinspeção – Nº de Série: {numero_serie}")

    df_checks = carregar_checklists()
    df_inspecao = df_checks[(df_checks["numero_serie"] == numero_serie) & (df_checks["reinspecao"] != "Sim")]
    if df_inspecao.empty:
        st.warning("Nenhum checklist de inspeção encontrado para reinspeção.")
        return False

    hoje = datetime.datetime.now(TZ).date()
    df_inspecao["data_hora"] = pd.to_datetime(df_inspecao["data_hora"])
    df_inspecao_mesmo_dia = df_inspecao[df_inspecao["data_hora"].dt.date == hoje]
    if df_inspecao_mesmo_dia.empty:
        st.warning("Nenhum checklist de inspeção encontrado para hoje.")
        return False

    checklist_original = df_inspecao_mesmo_dia.sort_values("data_hora").iloc[-1]

    perguntas = [
        "Etiqueta do produto – As informações estão corretas / legíveis conforme modelo e gravação do eixo?",
        "Placa do Inmetro está correta / fixada e legível? Número corresponde à viga?Gravação do número de série da viga está legível e pintada?",
        "Etiqueta do ABS está conforme? Com número de série compatível ao da viga? Teste do ABS está aprovado?",
        "Rodagem – tipo correto? Especifique o modelo",
        "Graxeiras e Anéis elásticos estão em perfeito estado?",
        "Sistema de atuação correto? Springs ou cuícas em perfeitas condições? Especifique o modelo:",
        "Catraca do freio correta? Especifique modelo",
        "Tampa do cubo correta, livre de avarias e pintura nos critérios? As tampas dos cubos dos ambos os lados são iguais?",
        "Pintura do eixo livre de oxidação,isento de escorrimento na pintura, pontos sem tinta e camada conforme padrão?",
        "Os cordões de solda do eixo estão conformes?"
    ]

    item_keys = {1: "ETIQUETA", 2: "PLACA_IMETRO E NÚMERO DE SÉRIE", 3: "TESTE_ABS", 4: "RODAGEM_MODELO", 5: "GRAXEIRAS E ANÉIS ELÁSTICOS", 6: "SISTEMA_ATUACAO", 7: "CATRACA_FREIO", 8: "TAMPA_CUBO", 9: "PINTURA_EIXO", 10: "SOLDA"}
    opcoes_modelos = {4:["Single","Aço","Alumínio","N/A"],6:["Spring","Cuíca","N/A"],7:["Automático","Manual","N/A"],10:["Conforme","Respingo","Falta de cordão","Porosidade","Falta de Fusão"]}
    resultados = {}
    modelos = {}

    st.write("Clique no botão correspondente a cada item:")
    st.caption("✅ = Conforme | ❌ = Não Conforme | 🟡 = N/A")

    with st.form(key=f"form_reinspecao_{numero_serie}"):
        for i, pergunta in enumerate(perguntas, start=1):
            cols = st.columns([7,2,2])
            chave = item_keys[i]

            status_antigo = checklist_original.get(chave, {}).get("status") if isinstance(checklist_original.get(chave), dict) else checklist_original.get(chave)
            obs_antigo = checklist_original.get(chave, {}).get("obs") if isinstance(checklist_original.get(chave), dict) else ""

            resp_antiga = "✅" if status_antigo=="Conforme" else "❌" if status_antigo=="Não Conforme" else "🟡"

            cols[0].markdown(f"**{i}. {pergunta}**")
            escolha = cols[1].radio(
                "",
                ["✅","❌","🟡"],
                key=f"resp_reinspecao_{numero_serie}_{i}",
                horizontal=True,
                index=["✅","❌","🟡"].index(resp_antiga),
                label_visibility="collapsed"
            )
            resultados[i] = escolha

            if i in opcoes_modelos:
                modelo = cols[2].selectbox(
                    "Modelo",
                    [""] + opcoes_modelos[i],
                    index=([""]+opcoes_modelos[i]).index(obs_antigo) if obs_antigo in opcoes_modelos[i] else 0,
                    key=f"modelo_reinspecao_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )
                modelos[i] = modelo
            else:
                modelos[i] = obs_antigo

        submit = st.form_submit_button("Salvar Reinspeção")
        if submit:
            dados_para_salvar = {}
            for i, resp in resultados.items():
                chave_item = item_keys[i]
                dados_para_salvar[chave_item] = {"status": status_emoji_para_texto(resp), "obs": modelos.get(i)}
            salvar_checklist(numero_serie, dados_para_salvar, usuario, reinspecao=True)
            st.success(f"Reinspeção do Nº de Série {numero_serie} salva com sucesso!")
            return True
    return False

# ==============================
# Interface principal
# ==============================
st.title("Sistema de Inspeção de Qualidade")

# Garantir que a chave 'usuario' esteja no session_state
if 'usuario' not in st.session_state:
    st.session_state['usuario'] = "default_usuario"  # Ou personalize conforme necessário

menu = st.sidebar.selectbox("Menu", ["Inspeção de Qualidade", "Reinspeção"])

if menu == "Inspeção de Qualidade":
    df_apont = carregar_apontamentos()
    hoje = datetime.datetime.now(TZ).date()

    if not df_apont.empty:
        start_of_day = TZ.localize(datetime.datetime.combine(hoje, datetime.time.min))
        end_of_day = TZ.localize(datetime.datetime.combine(hoje, datetime.time.max))
        df_hoje = df_apont[(df_apont["data_hora"] >= start_of_day) & (df_apont["data_hora"] <= end_of_day)]
        codigos_hoje = df_hoje["numero_serie"].unique()
    else:
        codigos_hoje = []

    df_checks = carregar_checklists()
    codigos_com_checklist = df_checks["numero_serie"].unique() if not df_checks.empty else []
    codigos_disponiveis = [c for c in codigos_hoje if c not in codigos_com_checklist]

    if codigos_disponiveis:
        numero_serie = st.selectbox("Selecione o Nº de Série para Inspeção", codigos_disponiveis, index=0)
        usuario = st.session_state['usuario']  # Agora a chave 'usuario' foi garantida
        checklist_qualidade(numero_serie, usuario)
    else:
        st.info("Nenhum código disponível para inspeção hoje.")

elif menu == "Reinspeção":
    usuario = st.session_state['usuario']  # Garantido
    df_checks = carregar_checklists()

    if df_checks.empty:
        st.info("Nenhum checklist registrado ainda.")
    else:
        df_reprovados = df_checks[(df_checks["produto_reprovado"] == "Sim") & (df_checks["reinspecao"] != "Sim")]
        numeros_serie_reinspecao = df_reprovados["numero_serie"].unique() if not df_reprovados.empty else []

        if len(numeros_serie_reinspecao) == 0:
            st.info("Nenhum checklist reprovado pendente para reinspeção.")
        else:
            numero_serie = st.selectbox("Selecione o Nº de Série para Reinspeção", numeros_serie_reinspecao, index=0)
            checklist_reinspecao(numero_serie, usuario)

