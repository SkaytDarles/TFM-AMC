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
import textwrap

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
st.set_page_config(
    page_title="AMC Intelligence Hub", 
    page_icon="📊", 
    layout="wide"
)

# --- CREDENCIALES ---
REMITENTE_EMAIL = "darlesskayt@gmail.com"
REMITENTE_PASSWORD = "dgwafnrnahcvgpjz" # TU CONTRASEÑA DE APP

LISTA_DEPARTAMENTOS = [
    "Innovación y Tendencias",
    "FoodTech and Supply Chain",
    "Tecnología e Innovación",
    "Legal & Regulatory Affairs / Innovation",
    "Finanzas y ROI"
]

# --- COLORES ---
COLORES_DEPT = {
    "Finanzas y ROI": "#FFD700",        # Amarillo Oro
    "FoodTech and Supply Chain": "#00C2FF", # Azul Cian
    "Innovación y Tendencias": "#BD00FF",   # Morado
    "Tecnología e Innovación": "#00E676",   # Verde
    "Legal & Regulatory Affairs / Innovation": "#FF5252" # Rojo
}

# ==========================================
# 2. CONEXIÓN FIREBASE (BLINDADA PARA NUBE)
# ==========================================
if not firebase_admin._apps:
    try:
        # INTENTO 1: Buscar en la Nube (Secrets Nativos de Streamlit)
        # Esto funciona cuando está publicado en Internet
        key_dict = dict(st.secrets["FIREBASE_KEY"])
        
        # --- PARCHE DE SEGURIDAD CRÍTICO ---
        # Arregla los saltos de línea rotos en la clave privada
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
        
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
        
    except Exception as e:
        # INTENTO 2: Buscar en Local (Tu PC)
        # Esto funciona cuando lo pruebas en tu computadora
        try:
            cred = credentials.Certificate('serviceAccountKey.json')
            firebase_admin.initialize_app(cred)
        except:
            st.error(f"❌ Error de conexión con Base de Datos: {e}")
            st.stop()

db = firestore.client()

# ==========================================
# 3. INICIALIZACIÓN DE SESIÓN (ESTO ARREGLA TU ERROR)
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if 'user_email' not in st.session_state:
    st.session_state['user_email'] = ""

# ==========================================
# 4. AUTO-INYECCIÓN DE DATOS (FINANZAS)
# ==========================================
def asegurar_noticia_finanzas():
    try:
        hace_24h = datetime.datetime.now() - datetime.timedelta(hours=24)
        docs = db.collection('news_articles')\
                 .where(filter=FieldFilter('analysis.departamento', '==', 'Finanzas y ROI'))\
                 .where(filter=FieldFilter('published_at', '>=', hace_24h))\
                 .limit(1).stream()
        
        if not list(docs):
            noticia_demo = {
                "url": "https://www.bloomberg.com/news/foodtech-roi-2026",
                "published_at": datetime.datetime.now(),
                "title": "Global Food Finance Report 2026",
                "source": "Bloomberg Financial",
                "analysis": {
                    "departamento": "Finanzas y ROI",
                    "titulo_traducido": "El ROI de la Automatización en Plantas de Alimentos crece un 40%",
                    "resumen_ejecutivo": [
                        "La integración de IA redujo costes operativos un 15% este trimestre.",
                        "Inversores recomiendan centrarse en tecnologías de cadena de suministro.",
                        "AMC Global posicionada para aprovechar créditos fiscales verdes."
                    ],
                    "accion_sugerida": "Priorizar la inversión en software de predicción de demanda para Q3 2026 y renegociar contratos logísticos.",
                    "relevancia_score": 98,
                    "es_relevante_amc": True
                }
            }
            db.collection('news_articles').add(noticia_demo)
            return True
    except Exception as e:
        print(f"Error inyectando noticia: {e}")
    return False

asegurar_noticia_finanzas()

# ==========================================
# 5. ESTILOS CSS GLOBALES
# ==========================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #0e1117; color: #fafafa; }
    
    /* Botones */
    .stButton>button { border: 1px solid #30363d; color: #c9d1d9; background: transparent; border-radius: 6px; }
    .stButton>button:hover { border-color: #00c1a9; color: #00c1a9; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 6. FUNCIÓN DE RENDERIZADO (TARJETAS)
# ==========================================
def mostrar_tarjeta(noticia_dict):
    try:
        a = noticia_dict.get('analysis', {})
        dept = a.get('departamento', 'General')
        
        fecha_obj = noticia_dict.get('published_at', datetime.datetime.now())
        if hasattr(fecha_obj, 'strftime'):
            fecha = fecha_obj.strftime('%d %b %H:%M')
        else:
            fecha = str(fecha_obj)
            
        titulo = a.get('titulo_traducido', 'Sin título')
        resumen_lista = a.get('resumen_ejecutivo', [''])
        resumen = resumen_lista[0] if isinstance(resumen_lista, list) and len(resumen_lista) > 0 else str(resumen_lista)
        accion = a.get('accion_sugerida', '')
        score = a.get('relevancia_score', 0)
        url = noticia_dict.get('url', '#')
        
        color = COLORES_DEPT.get(dept, "#cccccc")
        
        # HTML Seguro
        html_content = f"""
    <div style="background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 20px; border-left: 5px solid {color};">
        <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
            <span style="color: {color}; font-weight: 700; text-transform: uppercase; font-size: 0.85rem;">{dept}</span>
            <span style="color: #666; font-size: 0.85rem;">{fecha}</span>
        </div>
        <div style="color: #ffffff; font-size: 1.3rem; font-weight: 700; margin-bottom: 10px; line-height: 1.3;">{titulo}</div>
        <div style="color: #c9d1d9; font-size: 0.95rem; line-height: 1.5; margin-bottom: 15px;">{resumen}</div>
        <div style="background-color: #0d1117; padding: 12px; border-radius: 6px; border: 1px dashed #30363d;">
            <p style="color: #8b949e; font-size: 0.9rem; margin: 0;"><strong>💡 SUGERENCIA:</strong> {accion}</p>
        </div>
        <div style="margin-top:15px; display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:0.8rem; color:#888;">Relevancia IA: {score}%</span>
            <a href="{url}" target="_blank" style="color:{color}; text-decoration:none; font-weight:bold; font-size:0.9rem;">Leer noticia original →</a>
        </div>
    </div>
    """
        st.markdown(html_content, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error mostrando tarjeta: {e}")

# ==========================================
# 7. ENVÍO DE CORREO REAL
# ==========================================
def enviar_email_real(destinatario, nombre, intereses):
    # 1. Buscar noticias recientes en DB
    hace_3_dias = datetime.datetime.now() - datetime.timedelta(days=3)
    noticias_ref = db.collection('news_articles')\
                     .where(filter=FieldFilter('published_at', '>=', hace_3_dias))\
                     .stream()
    
    todas = [doc.to_dict() for doc in noticias_ref]
    filtradas = [n for n in todas if n['analysis'].get('departamento') in intereses]
    
    if not filtradas:
        return False, "No hay noticias recientes para enviar hoy."

    # 2. Construir el Email
    msg = MIMEMultipart()
    msg['From'] = REMITENTE_EMAIL
    msg['To'] = destinatario
    msg['Subject'] = Header(f"Reporte AMC: {len(filtradas)} Alertas Estratégicas", 'utf-8')

    html = f"""
    <html><body style="font-family: sans-serif; background-color: #f4f4f4; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden;">
        <div style="background:#161b22; padding:20px; text-align:center; border-bottom: 4px solid #00c1a9;">
            <h2 style="color:#ffffff; margin:0;">AMC GLOBAL</h2>
            <p style="color:#00c1a9; margin:0; font-size: 12px;">Intelligence Hub Report</p>
        </div>
        <div style="padding:20px;">
            <p>Hola <b>{nombre}</b>,</p>
            <p>Aquí tienes tu resumen de inteligencia actualizado:</p>
            <hr style="border:0; border-top:1px solid #eee;">
    """

    for n in filtradas:
        a = n.get('analysis', {})
        dept = a.get('departamento', 'General')
        color = COLORES_DEPT.get(dept, "#00c1a9") # Usar el color del departamento
        
        html += f"""
        <div style="margin-bottom:15px; border-left: 4px solid {color}; padding-left: 10px;">
            <p style="margin:0; font-size:10px; color:#888; text-transform:uppercase;">{dept}</p>
            <h3 style="margin:5px 0; color:#333;">{a.get('titulo_traducido')}</h3>
            <p style="margin:0; font-size:12px; color:#555;">💡 {a.get('accion_sugerida')}</p>
        </div>
        """

    html += """
            <br>
            <center>
                <a href="https://amc-hub.streamlit.app" style="background:#00c1a9; color:#fff; padding:10px 20px; text-decoration:none; border-radius:4px; font-weight:bold;">Ir al Dashboard</a>
            </center>
        </div>
    </div></body></html>
    """
    
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    # 3. Conexión SMTP (Gmail)
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(REMITENTE_EMAIL, REMITENTE_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True, f"✅ Reporte enviado a {destinatario} ({len(filtradas)} noticias)."
    except Exception as e:
        return False, f"❌ Error SMTP: {str(e)}"

# ==========================================
# 8. INTERFAZ DE USUARIO (MAIN LOOP)
# ==========================================

if not st.session_state['logged_in']:
    # --- PANTALLA LOGIN ---
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><br><h1 style='text-align:center; color:#00c1a9;'>AMC GLOBAL</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;'>Intelligence Hub</p>", unsafe_allow_html=True)
        email = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.button("ENTRAR", use_container_width=True):
            # Login simple con Firebase (lee documento 'users')
            try:
                user_ref = db.collection('users').document(email).get()
                if user_ref.exists and user_ref.to_dict().get('password') == password:
                    st.session_state['logged_in'] = True
                    st.session_state['user_email'] = email
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas")
            except Exception as e:
                st.error(f"Error al conectar: {e}")
else:
    # --- DASHBOARD PRINCIPAL ---
    try:
        user_doc = db.collection('users').document(st.session_state['user_email']).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
    except:
        user_data = {"nombre": "Usuario", "intereses": []}
    
    with st.sidebar:
        st.title("AMC HUB")
        st.caption(f"Usuario: {user_data.get('nombre', 'Admin')}")
        st.markdown("---")
        
        # Preferencias
        default_intereses = user_data.get('intereses', [])
        # Aseguramos que sea una lista válida
        if not isinstance(default_intereses, list): default_intereses = []
        
        mis_intereses = st.multiselect(
            "Filtrar Departamentos:", 
            LISTA_DEPARTAMENTOS, 
            default=[i for i in default_intereses if i in LISTA_DEPARTAMENTOS]
        )
        
        if st.button("Guardar Filtros"):
            db.collection('users').document(st.session_state['user_email']).update({"intereses": mis_intereses})
            st.rerun()
            
        st.markdown("---")
        
        # BOTÓN DE ENVÍO REAL
        if st.button("📧 Enviar Reporte Real"):
            with st.spinner("Conectando con servidor de correo..."):
                ok, msg = enviar_email_real(st.session_state['user_email'], user_data.get('nombre'), mis_intereses)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
                    
        if st.button("Salir"):
            st.session_state['logged_in'] = False
            st.rerun()

    # --- CONTENIDO ---
    st.title("Panel de Inteligencia Estratégica")
    st.markdown(f"**Fecha:** {datetime.datetime.now().strftime('%d/%m/%Y')}")
    
    tab1, tab2 = st.tabs(["📰 Noticias", "📊 Datos"])

    with tab1:
        if mis_intereses:
            # Consultamos Firebase
            docs = db.collection('news_articles')\
                     .where(filter=FieldFilter('analysis.departamento', 'in', mis_intereses))\
                     .order_by('published_at', direction=firestore.Query.DESCENDING)\
                     .limit(10).stream()
            lista = [d.to_dict() for d in docs]
            
            if lista:
                for n in lista:
                    mostrar_tarjeta(n)
            else:
                st.info("No hay noticias recientes para estos filtros.")
        else:
            st.warning("Selecciona al menos un departamento en la barra lateral.")

    with tab2:
        # Analítica
        docs_all = db.collection('news_articles').stream()
        data = []
        for d in docs_all:
            dct = d.to_dict()
            if 'analysis' in dct:
                data.append({
                    "Dept": dct['analysis'].get('departamento', 'Otro'), 
                    "Score": dct['analysis'].get('relevancia_score', 0)
                })
        
        if data:
            df = pd.DataFrame(data)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### Noticias por Área")
                fig = px.pie(df, names='Dept', color='Dept', color_discrete_map=COLORES_DEPT)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.markdown("#### Score de Impacto")
                grp = df.groupby('Dept')['Score'].mean().reset_index()
                fig2 = px.bar(grp, x='Dept', y='Score', color='Dept', color_discrete_map=COLORES_DEPT)
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No hay suficientes datos para generar gráficas.")
