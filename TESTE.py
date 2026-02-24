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
    return inicio_br.astimezone(UTC).isoformat(), fim_br.astimezone(UTC).isoformat()

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
        df["data_hora"] = pd.to_datetime(df["data_hora"], errors="coerce", utc=True).dt.tz_convert(TZ)
    return df

# ================================
# CHECKLIST – SALVAR
# ================================
def salvar_checklist(serie, resultados, usuario, rastreio_esq, rastreio_dir):
    inicio_utc, fim_utc = intervalo_hoje_utc()
    existe = (
        supabase.table("checklists")
        .select("numero_serie")
        .eq("numero_serie", serie)
        .gte("data_hora", inicio_utc)
        .lte("data_hora", fim_utc)
        .limit(100000)
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
            # ✅ NOVOS CAMPOS (precisam existir no Supabase)
            "rastreio_cubo_esquerdo": (rastreio_esq or "").strip(),
            "rastreio_cubo_direito": (rastreio_dir or "").strip(),
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
# CHECKLIST VISUAL
# ================================
def checklist_qualidade(numero_serie, usuario):
    st.markdown(f"## ✔️ Checklist de Qualidade – Nº Série: {numero_serie}")

    # ✅ NOVO BLOCO: Rastreio do cubo (esquerdo/direito)
    st.markdown("### 🔎 Qual o número de rastreio do cubo?")
    col1, col2 = st.columns(2)

    with col1:
        rastreio_esq = st.text_input(
            "Lado Esquerdo",
            key=f"rastreio_esq_{numero_serie}"
        )

    with col2:
        rastreio_dir = st.text_input(
            "Lado Direito",
            key=f"rastreio_dir_{numero_serie}"
        )

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

    item_keys = {i+1: k for i, k in enumerate([
        "ETIQUETA", "PLACA_INMETRO", "TESTE_ABS", "RODAGEM",
        "GRAXEIRAS", "SISTEMA_ATUACAO", "CATRACA", "TAMPA_CUBO",
        "PINTURA", "SOLDA"
    ])}

    resultados = {}
    with st.form(f"form_{numero_serie}"):
        for i, pergunta in enumerate(perguntas, 1):
            cols = st.columns([7, 3])
            cols[0].markdown(f"**{i}. {pergunta}**")
            resultados[i] = cols[1].radio(
                "", ["", "✅", "❌", "🟡"],  # opção vazia obrigando escolha
                horizontal=True,
                key=f"{numero_serie}_{i}",
                label_visibility="collapsed"
            )

        salvar = st.form_submit_button("💾 Salvar Checklist")

    if salvar:
        if any(resultados[i] == "" for i in resultados):
            st.error("⚠️ Você precisa selecionar uma opção para todas as perguntas antes de salvar.")
            return

        dados = {item_keys[i]: {"status": status_emoji_para_texto(resultados[i]), "obs": ""} for i in resultados}
        salvar_checklist(numero_serie, dados, usuario, rastreio_esq, rastreio_dir)

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

    df_hoje["numero_serie"] = df_hoje["numero_serie"].astype(str).str.strip()

    inicio_utc, fim_utc = intervalo_hoje_utc()
    series_inspecionadas_hoje = set()
    offset = 0
    batch = 1000
    while True:
        res = (
            supabase.table("checklists")
            .select("numero_serie")
            .gte("data_hora", inicio_utc)
            .lte("data_hora", fim_utc)
            .range(offset, offset + batch - 1)
            .execute()
        )
        if not res.data:
            break
        series_inspecionadas_hoje.update(str(r["numero_serie"]).strip() for r in res.data)
        offset += batch

    if "series_concluidas" not in st.session_state:
        st.session_state.series_concluidas = set()
    else:
        st.session_state.series_concluidas = {str(s).strip() for s in st.session_state.series_concluidas}

    df_pendentes = df_hoje[
        ~df_hoje["numero_serie"].isin(series_inspecionadas_hoje | st.session_state.series_concluidas)
    ]

    if df_pendentes.empty:
        st.success("✅ Todos os apontamentos de hoje já foram inspecionados")
        return

    # --- ORDENANDO pelo mais antigo primeiro ---
    df_pendentes = df_pendentes.sort_values("data_hora", ascending=True)
    serie = st.selectbox(
        "Selecione o Nº de Série",
        sorted(
            df_pendentes["numero_serie"].unique(),
            key=lambda x: df_pendentes[df_pendentes["numero_serie"] == x]["data_hora"].iloc[0]
        )
    )

    checklist_qualidade(serie, st.session_state.usuario)

# ================================
# START
# ================================
if __name__ == "__main__":
    app()


