import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
import pandas as pd
import plotly.express as px
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import time
import json
import hashlib
import google.generativeai as genai
from duckduckgo_search import DDGS

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS (UI/UX FINAL)
# ==========================================
st.set_page_config(
    page_title="AMC Intelligence Hub", 
    page_icon="🔓", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS PERSONALIZADO (BOTONES, TABS, CHECKBOXES) ---
st.markdown("""
<style>
    /* Botones Estilo Cyber/Teal */
    div.stButton > button {
        background-color: #0d1117; 
        color: #00c1a9;
        border: 1px solid #00c1a9;
        border-radius: 6px;
        transition: all 0.3s ease;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    div.stButton > button:hover {
        background-color: #00c1a9;
        color: #ffffff;
        box-shadow: 0px 0px 10px rgba(0, 193, 169, 0.5);
        border-color: #00c1a9;
    }
    div.stButton > button:active { transform: scale(0.98); }

    /* Pestañas (Tabs) Dark Mode */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] {
        height: 50px; background-color: #0d1117; color: #8b949e;
        border: 1px solid #30363d; border-radius: 6px 6px 0px 0px;
        padding: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #161b22 !important; color: #00c1a9 !important;
        border: 1px solid #00c1a9; border-bottom: none;
    }

    /* Tipografía y Colores */
    h1 { color: #00c1a9 !important; }
    h2, h3 { color: #e6edf3 !important; }
    p, span, div, label { color: #c9d1d9; }
    
    /* Inputs */
    .stTextInput > div > div > input {
        background-color: #0d1117; color: white; border-color: #30363d;
    }
    
    /* Badges */
    .ia-badge {
        background-color: #21262d; padding: 4px 10px; border-radius: 12px;
        font-size: 0.8rem; border: 1px solid #30363d; display: inline-block; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTES ---
REMITENTE_EMAIL = "darlesskayt@gmail.com"
REMITENTE_PASSWORD = "dgwafnrnahcvgpjz" 

# CONFIGURACIÓN DEL UMBRAL DE CONFIANZA
MIN_SCORE_IA = 75

LISTA_DEPARTAMENTOS = [
    "Finanzas y ROI", 
    "FoodTech and Supply Chain", 
    "Innovación y Tendencias", 
    "Tecnología e Innovación", 
    "Legal & Regulatory Affairs / Innovation"
]

COLORES_DEPT = {
    "Finanzas y ROI": "#FFD700", "FoodTech and Supply Chain": "#00C2FF",
    "Innovación y Tendencias": "#BD00FF", "Tecnología e Innovación": "#00E676",
    "Legal & Regulatory Affairs / Innovation": "#FF5252"
}

QUERIES_DEPT = {
    "Finanzas y ROI": "retorno inversión automatización alimentos",
    "FoodTech and Supply Chain": "tecnología cadena suministro alimentos",
    "Innovación y Tendencias": "tendencias industria alimentos 2025",
    "Tecnología e Innovación": "inteligencia artificial manufactura industrial",
    "Legal & Regulatory Affairs / Innovation": "ley etiquetado alimentos normativa tecnología"
}

# ==========================================
# 2. UTILIDADES DE CONEXIÓN Y DATOS
# ==========================================
def hash_pass(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def limpiar_json(texto):
    try:
        start = texto.find('{')
        end = texto.rfind('}') + 1
        if start != -1 and end != 0:
            return json.loads(texto[start:end])
        return None
    except: return None

@st.cache_resource
def init_connection():
    try:
        if not firebase_admin._apps:
            if "FIREBASE_KEY" in st.secrets:
                key_dict = dict(st.secrets["FIREBASE_KEY"])
                if "private_key" in key_dict:
                    key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)
            else:
                cred = credentials.Certificate('serviceAccountKey.json')
                firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"❌ Error DB: {e}")
        return None

db = init_connection()

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# ==========================================
# 3. LÓGICA DE NEGOCIO (IA & SCRAPING)
# ==========================================
def analizar_con_gemini(texto, titulo, dept):
    if "GOOGLE_API_KEY" not in st.secrets:
        return {"titulo_mejorado": titulo, "resumen": texto[:200], "accion": "Configurar API Key", "score": 50}

    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    Analista AMC Global ({dept}).
    Noticia: {titulo}
    Texto: {texto[:800]}...

    Output JSON:
    {{
        "titulo_mejorado": "Título breve español",
        "resumen": "Resumen ejecutivo 30 palabras.",
        "accion": "Sugerencia estratégica.",
        "score": (0-100 entero)
    }}
    """
    try:
        response = model.generate_content(prompt)
        data = limpiar_json(response.text)
        if data: return data
    except: pass
    
    return {"titulo_mejorado": titulo, "resumen": "Error IA", "accion": "Revisar", "score": 50}

def buscador_inteligente():
    count_news = 0
    ddgs = DDGS()
    
    progress_text = "🕵️ Iniciando escaneo de fuentes abiertas..."
    my_bar = st.progress(0, text=progress_text)
    total_steps = len(QUERIES_DEPT)
    current_step = 0
    
    for dept, query in QUERIES_DEPT.items():
        current_step += 1
        my_bar.progress(int((current_step / total_steps) * 100), text=f"Escaneando: {dept}")
        
        try:
            # Busqueda
            resultados = list(ddgs.text(f"{query} noticias recientes", region="wt-wt", timelimit="d", max_results=2))
            
            for r in resultados:
                titulo = r.get('title')
                link = r.get('href')
                body = r.get('body')

                if not titulo or not link: continue
                
                # Duplicados
                docs = db.collection('news_articles').where(filter=FieldFilter('title', '==', titulo)).limit(1).stream()
                if list(docs): continue

                # Análisis IA
                analisis = analizar_con_gemini(body, titulo, dept)
                
                # Guardar
                db.collection('news_articles').add({
                    "title": analisis.get('titulo_mejorado', titulo),
                    "url": link,
                    "published_at": datetime.datetime.now(),
                    "source": "Web Abierta",
                    "analysis": {
                        "departamento": dept,
                        "resumen_ejecutivo": analisis.get('resumen'),
                        "accion_sugerida": analisis.get('accion'),
                        "relevancia_score": analisis.get('score')
                    }
                })
                count_news += 1
                time.sleep(0.5)
        except: continue

    my_bar.empty()
    return count_news

# ==========================================
# 4. EMAIL INTELIGENTE (ASUNTO DINÁMICO)
# ==========================================
def enviar_reporte_email(news_list, dest, nombre, areas_contexto):
    if not news_list: return False
    
    # Asunto Dinámico
    fecha_str = datetime.datetime.now().strftime("%d %b")
    # Calcular categoría dominante o general
    deptos = list(set([n['analysis']['departamento'] for n in news_list]))
    cat_str = deptos[0] if len(deptos) == 1 else "Resumen Ejecutivo"
    
    subject = f"AMC Daily: {cat_str} - {fecha_str}"

    try:
        msg = MIMEMultipart()
        msg['From'] = REMITENTE_EMAIL
        msg['To'] = dest
        msg['Subject'] = Header(subject, 'utf-8')

        rows = ""
        for n in news_list:
            analisis = n.get('analysis', {})
            color = COLORES_DEPT.get(analisis.get('departamento'), "#333")
            rows += f"""
            <tr>
                <td style="padding:15px; border-bottom:1px solid #eee;">
                    <span style="color:{color}; font-size:10px; font-weight:bold;">{analisis.get('departamento', '').upper()}</span>
                    <h3 style="margin:5px 0; color:#333;">{n.get('title')}</h3>
                    <p style="color:#666; font-size:14px;">{analisis.get('resumen_ejecutivo')}</p>
                    <a href="{n.get('url')}" style="color:#00c1a9; text-decoration:none; font-size:12px;">🔗 Leer fuente</a>
                </td>
            </tr>
            """

        html = f"""
        <div style="font-family:Helvetica, sans-serif; max-width:600px; margin:0 auto; border:1px solid #e0e0e0;">
            <div style="background:#161b22; padding:20px; text-align:center;">
                <h2 style="color:#00c1a9; margin:0;">AMC INTELLIGENCE</h2>
                <p style="color:#888; font-size:12px;">{fecha_str}</p>
            </div>
            <div style="padding:20px;">
                <p>Hola {nombre}, aquí tienes tu selección de noticias:</p>
                <table style="width:100%; border-collapse:collapse;">{rows}</table>
            </div>
        </div>
        """
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(REMITENTE_EMAIL, REMITENTE_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(e)
        return False

# ==========================================
# 5. PANTALLA DE ACCESO (LOGIN/REGISTRO)
# ==========================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'user_info' not in st.session_state: st.session_state['user_info'] = {}

def main_login():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><h1 style='text-align:center;'>AMC GLOBAL</h1>", unsafe_allow_html=True)
        tab1, tab2 = st.tabs(["🔐 INGRESAR", "📝 REGISTRARSE"])
        
        with tab1:
            with st.form("login_form"):
                email = st.text_input("Usuario (Email)")
                password = st.text_input("Contraseña", type="password")
                if st.form_submit_button("ACCESO"):
                    if not db: st.stop()
                    doc = db.collection('users').document(email).get()
                    if doc.exists:
                        data = doc.to_dict()
                        if data.get('password') == hash_pass(password):
                            st.session_state['logged_in'] = True
                            st.session_state['user_email'] = email
                            st.session_state['user_info'] = data
                            st.rerun()
                        else: st.error("Contraseña incorrecta.")
                    else: st.error("Usuario no encontrado.")

        with tab2:
            with st.form("register_form"):
                st.markdown("### Nueva Cuenta")
                new_email = st.text_input("Email Corporativo")
                new_name = st.text_input("Nombre Completo")
                new_pass = st.text_input("Definir Contraseña", type="password")
                
                st.markdown("**Intereses:**")
                new_intereses = st.multiselect("Departamentos", LISTA_DEPARTAMENTOS, default=LISTA_DEPARTAMENTOS)
                
                if st.form_submit_button("CREAR CUENTA"):
                    if new_email and new_name and new_pass:
                        if not db.collection('users').document(new_email).get().exists:
                            final_intereses = new_intereses if new_intereses else LISTA_DEPARTAMENTOS
                            db.collection('users').document(new_email).set({
                                "nombre": new_name, 
                                "password": hash_pass(new_pass),
                                "intereses": final_intereses, 
                                "created_at": datetime.datetime.now()
                            })
                            st.success("Cuenta creada. Ingresa en la pestaña 'INGRESAR'.")
                        else: st.warning("Usuario ya existe.")

# ==========================================
# 6. DASHBOARD PRINCIPAL (HUMAN-IN-THE-LOOP)
# ==========================================
def main_app():
    user = st.session_state['user_info']
    
    # Estado para selección de noticias (Checkboxes)
    if 'selected_news' not in st.session_state:
        st.session_state['selected_news'] = set()

    # --- SIDEBAR ---
    with st.sidebar:
        st.title("AMC HUB")
        st.caption(f"👤 {user.get('nombre', 'Analista')}")
        
        if st.button("🚪 Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()
            
        st.divider()
        filtro_tiempo = st.radio("Período:", ["Hoy (Tiempo Real)", "Ayer", "Histórico 7 días"])
        mis_intereses = st.multiselect("Filtro Áreas:", LISTA_DEPARTAMENTOS, default=user.get('intereses', [])[:3])
        
        st.divider()
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔄 Escanear"):
                with st.spinner("Buscando..."):
                    n = buscador_inteligente()
                    st.toast(f"Escaneo completado: {n} noticias.", icon="✅")
                    time.sleep(1)
                    st.rerun()
        with col_btn2:
            if st.button("💾 Guardar"):
                db.collection('users').document(st.session_state['user_email']).update({"intereses": mis_intereses})
                st.session_state['user_info']['intereses'] = mis_intereses
                st.toast("Preferencias guardadas")

        st.markdown("---")
        
        # BOTÓN DE ENVÍO DE SELECCIÓN
        count_sel = len(st.session_state['selected_news'])
        label_email = f"📧 Enviar ({count_sel})" if count_sel > 0 else "📧 Enviar Selección"
        
        if st.button(label_email, disabled=(count_sel == 0)):
            # Recuperar objetos completos de cache
            if 'news_cache' in st.session_state:
                to_send = [n for n in st.session_state['news_cache'] if n['title'] in st.session_state['selected_news']]
                
                with st.spinner("Enviando newsletter..."):
                    exito = enviar_reporte_email(to_send, st.session_state['user_email'], user.get('nombre'), mis_intereses)
                
                if exito:
                    st.toast(f"¡Enviado con éxito a {st.session_state['user_email']}!", icon="🚀")
                    st.session_state['selected_news'] = set() # Limpiar
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Error al enviar.")

    # --- CONTENIDO CENTRAL ---
    st.title("Centro de Inteligencia")
    
    # Query Data
    hoy = datetime.datetime.now().replace(hour=0, minute=0, second=0)
    query = db.collection('news_articles')
    if mis_intereses: query = query.where(filter=FieldFilter('analysis.departamento', 'in', mis_intereses))
    
    if filtro_tiempo == "Hoy (Tiempo Real)": query = query.where(filter=FieldFilter('published_at', '>=', hoy))
    elif filtro_tiempo == "Ayer": 
        ayer = hoy - datetime.timedelta(days=1)
        query = query.where(filter=FieldFilter('published_at', '>=', ayer)).where(filter=FieldFilter('published_at', '<', hoy))
    
    docs = query.order_by('published_at', direction=firestore.Query.DESCENDING).limit(50).stream()
    lista_noticias = [d.to_dict() for d in docs]
    st.session_state['news_cache'] = lista_noticias # Cachear para envío email

    tab_news, tab_metrics = st.tabs(["📰 Feed de Noticias", "📊 Métricas"])
    
    with tab_news:
        if not lista_noticias:
            st.info("📭 Sin noticias. Usa el botón '🔄 Escanear' en la barra lateral.")
        else:
            # BOTÓN "AUTO-SELECT TOP IA" (MODIFICADO A 75%)
            col_ia_1, col_ia_2 = st.columns([3, 1])
            with col_ia_2:
                if st.button(f"✨ Auto-selección IA (>{MIN_SCORE_IA})"):
                    added = 0
                    for n in lista_noticias:
                        if n['analysis'].get('relevancia_score', 0) > MIN_SCORE_IA:
                            st.session_state['selected_news'].add(n['title'])
                            added += 1
                    st.toast(f"IA seleccionó {added} noticias relevantes.", icon="🤖")
                    time.sleep(1)
                    st.rerun()

            # RENDER LISTA
            for n in lista_noticias:
                title = n.get('title')
                a = n.get('analysis', {})
                dept = a.get('departamento', 'General')
                color = COLORES_DEPT.get(dept, '#888')
                score = a.get('relevancia_score', 0)
                
                # Checkbox
                is_checked = title in st.session_state['selected_news']
                
                with st.container():
                    c_chk, c_line, c_content = st.columns([0.2, 0.1, 4])
                    with c_chk:
                        # Usamos key única
                        if st.checkbox("", value=is_checked, key=f"chk_{title}"):
                            st.session_state['selected_news'].add(title)
                        else:
                            st.session_state['selected_news'].discard(title)
                            
                    with c_line:
                        st.markdown(f"<div style='height:100%; width:4px; background-color:{color}; border-radius:4px;'></div>", unsafe_allow_html=True)
                    
                    with c_content:
                        st.markdown(f"### [{title}]({n.get('url')})")
                        st.caption(f"**{dept}** • {n.get('published_at').strftime('%H:%M')}")
                        st.markdown(f"{a.get('resumen_ejecutivo', '...')}")
                        
                        # IA Badge + Acción (MODIFICADO A 75%)
                        badge_color = "#00E676" if score > MIN_SCORE_IA else "#c9d1d9"
                        border_color = "#00E676" if score > MIN_SCORE_IA else "#444"
                        
                        st.markdown(f"""
                        <div style="margin-top:10px; display:flex; gap:10px;">
                            <span style="background:rgba(0,193,169,0.1); color:#00c1a9; padding:2px 8px; border-radius:4px; font-size:0.85em;">
                                💡 {a.get('accion_sugerida', 'Revisar')}
                            </span>
                            <span class="ia-badge" style="color:{badge_color}; border-color:{border_color};">
                                IA Score: {score}/100
                            </span>
                        </div>
                        """, unsafe_allow_html=True)
                    st.divider()

    with tab_metrics:
        if lista_noticias:
            df = pd.DataFrame([n['analysis'] for n in lista_noticias if 'analysis' in n])
            if not df.empty:
                c1, c2 = st.columns(2)
                with c1: st.plotly_chart(px.pie(df, names='departamento', color='departamento', color_discrete_map=COLORES_DEPT, hole=0.4), use_container_width=True)
                with c2: st.plotly_chart(px.bar(df.groupby('departamento')['relevancia_score'].mean().reset_index(), x='departamento', y='relevancia_score', color='departamento', color_discrete_map=COLORES_DEPT), use_container_width=True)

if __name__ == "__main__":
    if st.session_state['logged_in']: main_app()
    else: main_login()
