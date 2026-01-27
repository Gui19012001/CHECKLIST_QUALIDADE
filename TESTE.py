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
UTC = pytz.utc

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
# INTERVALO UTC DO DIA (BR)
# ================================
def intervalo_hoje_utc():
    hoje_br = datetime.datetime.now(TZ).date()

    inicio_br = TZ.localize(datetime.datetime.combine(hoje_br, datetime.time.min))
    fim_br    = TZ.localize(datetime.datetime.combine(hoje_br, datetime.time.max))

    return (
        inicio_br.astimezone(UTC).isoformat(),
        fim_br.astimezone(UTC).isoformat()
    )

# ================================
# CACHE – APONTAMENTOS
# ================================
@st.cache_data(ttl=30)
def carregar_apontamentos():
    res = (
        supabase.table("apontamentos")
        .select("*")
        .order("data_hora", desc=True)
        .limit(500)
        .execute()
    )

    df = pd.DataFrame(res.data)

    if not df.empty:
        df["data_hora"] = pd.to_datetime(
            df["data_hora"],
            errors="coerce",
            utc=True
        ).dt.tz_convert(TZ)

    return df

# ================================
# CHECKLIST – SALVAR (BLOQUEIO REAL)
# ================================
def salvar_checklist(serie, resultados, usuario):

    inicio_utc, fim_utc = intervalo_hoje_utc()

    existe = (
        supabase.table("checklists")
        .select("id")
        .eq("numero_serie", serie)
        .gte("data_hora", inicio_utc)
        .lte("data_hora", fim_utc)
        .limit(1000)
        .execute()
    )

    if existe.data:
        st.error("⚠️ Este Nº de Série já foi inspecionado hoje.")
        return

    data_hora = datetime.datetime.now(UTC).isoformat()
    reprovado = any(v["status"] == "Não Conforme" for v in resultados.values())

    registros = [
        {
            "numero_serie": serie,
            "item": item,
            "status": info["status"],
            "observacoes": info["obs"],
            "inspetor": usuario,
            "produto_reprovado": "Sim" if reprovado else "Não",
            "data_hora": data_hora
        }
        for item, info in resultados.items()
    ]

    supabase.table("checklists").insert(registros).execute()

    st.cache_data.clear()
    st.session_state.series_concluidas.add(serie)

    st.success(f"✅ Checklist salvo – Série {serie}")
    st.rerun()

# ================================
# UTIL
# ================================
def status_emoji_para_texto(emoji):
    return {"✅": "Conforme", "❌": "Não Conforme", "🟡": "N/A"}.get(emoji)

# ================================
# CHECKLIST VISUAL (INALTERADO)
# ================================
def checklist_qualidade(numero_serie, usuario):

    st.markdown(f"## ✔️ Checklist de Qualidade – Nº Série: {numero_serie}")

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
            cols = st.columns([7, 3])
            cols[0].markdown(f"**{i}. {pergunta}**")

            resultados[i] = cols[1].radio(
                "",
                ["✅", "❌", "🟡"],
                horizontal=True,
                key=f"{numero_serie}_{i}",
                index=None,
                label_visibility="collapsed"
            )

        salvar = st.form_submit_button("💾 Salvar Checklist")

    if salvar:
        dados = {
            item_keys[i]: {
                "status": status_emoji_para_texto(resultados[i]),
                "obs": ""
            }
            for i in resultados
        }

        salvar_checklist(numero_serie, dados, usuario)

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

    df_apont = carregar_apontamentos()
    hoje = datetime.datetime.now(TZ).date()

    df_hoje = df_apont[df_apont["data_hora"].dt.date == hoje]

    if df_hoje.empty:
        st.info("Nenhum apontamento hoje")
        return

    inicio_utc, fim_utc = intervalo_hoje_utc()

    res = (
        supabase.table("checklists")
        .select("numero_serie")
        .gte("data_hora", inicio_utc)
        .lte("data_hora", fim_utc)
        .execute()
    )

    series_inspecionadas_hoje = {
        r["numero_serie"] for r in res.data
    } if res.data else set()

    df_pendentes = df_hoje[
        ~df_hoje["numero_serie"].isin(
            series_inspecionadas_hoje | st.session_state.series_concluidas
        )
    ]

    if df_pendentes.empty:
        st.success("✅ Todos os apontamentos de hoje já foram inspecionados")
        return

    serie = st.selectbox(
        "Selecione o Nº de Série",
        sorted(df_pendentes["numero_serie"].unique())
    )

    checklist_qualidade(serie, st.session_state.usuario)

# ================================
# START
# ================================
if __name__ == "__main__":
    app()

