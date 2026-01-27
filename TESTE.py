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
        df["data_hora"] = pd.to_datetime(df["data_hora"], utc=True).dt.tz_convert(TZ)

    return df


# ================================
# CHECKLIST – SALVAR (BLINDADO)
# ================================
def salvar_checklist(serie, resultados, usuario):

    hoje = datetime.datetime.now(TZ).date()
    hoje_str = hoje.strftime("%Y-%m-%d")

    # 🔒 BLOQUEIO DEFINITIVO – JÁ EXISTE HOJE?
    existe = (
        supabase.table("checklists")
        .select("id")
        .eq("numero_serie", serie)
        .gte("data_hora", f"{hoje_str}T00:00:00")
        .lte("data_hora", f"{hoje_str}T23:59:59")
        .limit(1)
        .execute()
    )

    if existe.data:
        st.error("⚠️ Checklist já salvo hoje para esta série.")
        return False

    data_hora = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reprovado = any(v["status"] == "Não Conforme" for v in resultados.values())

    registros = []
    for item, info in resultados.items():
        registros.append({
            "numero_serie": serie,
            "item": item,
            "status": info["status"],
            "observacoes": info["obs"],
            "inspetor": usuario,
            "produto_reprovado": "Sim" if reprovado else "Não",
            "data_hora": data_hora
        })

    supabase.table("checklists").insert(registros).execute()

    # 🔄 LIMPA TUDO
    st.cache_data.clear()
    st.session_state["salvo"] = True

    return True


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

    with st.form(f"form_{numero_serie}", clear_on_submit=False):
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

    if salvar and not st.session_state.get("salvo"):
        dados = {
            item_keys[i]: {
                "status": status_emoji_para_texto(resultados[i]),
                "obs": ""
            }
            for i in resultados
        }

        if salvar_checklist(numero_serie, dados, usuario):
            st.success("✅ Checklist salvo com sucesso")
            st.rerun()


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
                st.session_state["salvo"] = False
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos")

        st.stop()


# ================================
# APP
# ================================
def app():
    login()

    st.session_state.setdefault("salvo", False)

    df_apont = carregar_apontamentos()
    hoje = datetime.datetime.now(TZ).date()
    df_hoje = df_apont[df_apont["data_hora"].dt.date == hoje]

    if df_hoje.empty:
        st.info("Nenhum apontamento hoje")
        return

    hoje_str = hoje.strftime("%Y-%m-%d")

    res = (
        supabase.table("checklists")
        .select("numero_serie")
        .gte("data_hora", f"{hoje_str}T00:00:00")
        .lte("data_hora", f"{hoje_str}T23:59:59")
        .execute()
    )

    if res.data:
        df_check = pd.DataFrame(res.data)
        df_pendentes = df_hoje.merge(
            df_check,
            on="numero_serie",
            how="left",
            indicator=True
        ).query('_merge == "left_only"').drop(columns="_merge")
    else:
        df_pendentes = df_hoje.copy()

    if df_pendentes.empty:
        st.success("✅ Todos os apontamentos de hoje já foram inspecionados")
        return

    serie = st.selectbox(
        "Selecione o Nº de Série",
        df_pendentes["numero_serie"].unique()
    )

    checklist_qualidade(serie, st.session_state.usuario)


if __name__ == "__main__":
    app()

