import streamlit as st
import pandas as pd
import datetime
import pytz
from supabase import create_client
import os
from dotenv import load_dotenv
from pathlib import Path

# ================================
# CONFIG
# ================================
st.set_page_config(page_title="Controle de Qualidade", layout="wide")

TZ = pytz.timezone("America/Sao_Paulo")

usuarios = {
    "admin": "admin",
    "Maria": "maria",
    "Catia": "catia",
    "Vera": "vera",
    "Bruno": "bruno"
}

# ================================
# ENV
# ================================
env_path = Path(__file__).parent / "teste.env"
load_dotenv(env_path)

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# ================================
# CACHE DE LEITURA
# ================================
@st.cache_data(ttl=60)
def carregar_apontamentos_hoje():
    hoje_utc = datetime.datetime.now(TZ).astimezone(pytz.UTC).date().isoformat()

    res = supabase.table("apontamentos") \
        .select("numero_serie,data_hora") \
        .gte("data_hora", hoje_utc) \
        .execute()

    df = pd.DataFrame(res.data)

    if not df.empty:
        df["data_hora"] = pd.to_datetime(
            df["data_hora"],
            utc=True,
            format="ISO8601",
            errors="coerce"
        ).dt.tz_convert(TZ)

    return df


@st.cache_data(ttl=60)
def carregar_series_inspecionadas_hoje():
    """
    Retorna APENAS as séries inspecionadas HOJE,
    usando data_hora >= início do dia local (convertido para UTC)
    e garantindo DISTINCT por numero_serie.
    """
    inicio_dia_local = datetime.datetime.now(TZ).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    inicio_dia_utc = inicio_dia_local.astimezone(pytz.UTC).isoformat()

    res = supabase.table("checklists") \
        .select("numero_serie") \
        .gte("data_hora", inicio_dia_utc) \
        .execute()

    # DISTINCT manual (Supabase Python não tem distinct nativo)
    return set(r["numero_serie"] for r in res.data) if res.data else set()


# ================================
# CHECKLIST – SALVAMENTO
# ================================
def salvar_checklist(serie, resultados, usuario):

    hoje_utc = datetime.datetime.now(TZ).astimezone(pytz.UTC).date().isoformat()

    existe = supabase.table("checklists") \
        .select("id") \
        .eq("numero_serie", serie) \
        .gte("data_hora", hoje_utc) \
        .limit(1) \
        .execute()

    if existe.data:
        st.error("⚠️ INVÁLIDO! DUPLICIDADE – Este Nº de Série já foi inspecionado hoje.")
        return

    reprovado = any(v["status"] == "Não Conforme" for v in resultados.values())
    data_hora = datetime.datetime.now(TZ).astimezone(pytz.UTC).isoformat()

    registros = []

    for item, info in resultados.items():
        registros.append({
            "numero_serie": serie,
            "item": item,
            "status": info["status"],
            "observacoes": info["obs"],
            "inspetor": usuario,
            "data_hora": data_hora,
            "produto_reprovado": "Sim" if reprovado else "Não"
        })

    supabase.table("checklists").insert(registros).execute()

    # 🔥 ATUALIZA ESTADO IMEDIATO
    st.cache_data.clear()
    st.session_state.series_concluidas.add(serie)

    st.success(f"✅ Checklist salvo – Nº Série {serie}")
    st.rerun()


# ================================
# UTIL
# ================================
def status_emoji_para_texto(emoji):
    if emoji == "✅":
        return "Conforme"
    if emoji == "❌":
        return "Não Conforme"
    return "N/A"


# ================================
# CHECKLIST VISUAL (INALTERADO)
# ================================
def checklist_qualidade(numero_serie, usuario):

    st.markdown(f"## ✔️ Checklist de Qualidade – Nº de Série: {numero_serie}")

    perguntas = [
        "Etiqueta do produto – As informações estão corretas?",
        "Placa do Inmetro conforme?",
        "Etiqueta do ABS conforme?",
        "Rodagem – tipo correto?",
        "Graxeiras e anéis em perfeito estado?",
        "Sistema de atuação correto?",
        "Catraca do freio correta?",
        "Tampa do cubo correta?",
        "Pintura conforme padrão?",
        "Cordões de solda conformes?"
    ]

    item_keys = {
        1: "ETIQUETA",
        2: "PLACA_INMETRO",
        3: "TESTE_ABS",
        4: "RODAGEM",
        5: "GRAXEIRAS",
        6: "SISTEMA_ATUACAO",
        7: "CATRACA",
        8: "TAMPA_CUBO",
        9: "PINTURA",
        10: "SOLDA"
    }

    resultados = {}

    with st.form(f"form_{numero_serie}"):
        for i, pergunta in enumerate(perguntas, 1):
            cols = st.columns([7, 2])
            cols[0].markdown(f"**{i}. {pergunta}**")

            resultados[item_keys[i]] = {
                "status": status_emoji_para_texto(
                    cols[1].radio(
                        "",
                        ["✅", "❌", "🟡"],
                        horizontal=True,
                        key=f"{numero_serie}_{i}",
                        index=None,
                        label_visibility="collapsed"
                    )
                ),
                "obs": None
            }

        salvar = st.form_submit_button("💾 Salvar Checklist")

    if salvar:
        salvar_checklist(numero_serie, resultados, st.session_state.usuario)


# ================================
# LOGIN
# ================================
def login():
    if "logado" not in st.session_state:
        st.session_state.logado = False

    if not st.session_state.logado:
        user = st.text_input("Usuário")
        pwd = st.text_input("Senha", type="password")

        if st.button("Entrar"):
            if usuarios.get(user) == pwd:
                st.session_state.logado = True
                st.session_state.usuario = user
                st.session_state.series_concluidas = set()
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos")

        st.stop()


# ================================
# APP
# ================================
def app():
    login()

    st.sidebar.selectbox("Menu", ["Inspeção de Qualidade"])

    df_apont = carregar_apontamentos_hoje()
    series_inspecionadas = carregar_series_inspecionadas_hoje()

    codigos = df_apont["numero_serie"].unique().tolist() if not df_apont.empty else []

    disponiveis = [
        c for c in codigos
        if c not in series_inspecionadas
        and c not in st.session_state.series_concluidas
    ]

    if disponiveis:
        serie = st.selectbox("Selecione o Nº de Série", disponiveis)
        checklist_qualidade(serie, st.session_state.usuario)
    else:
        st.info("Nenhum código disponível para inspeção.")


if __name__ == "__main__":
    app()
