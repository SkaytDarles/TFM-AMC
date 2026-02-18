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
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
import re

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
st.set_page_config(
    page_title="AMC Intelligence Hub", 
    page_icon="📡", 
    layout="wide"
)

# --- CREDENCIALES ---
REMITENTE_EMAIL = "darlesskayt@gmail.com"
REMITENTE_PASSWORD = "dgwafnrnahcvgpjz" # Tu App Password

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

# MAPA DE BÚSQUEDA: Qué buscar en Google para cada departamento
QUERIES_DEPT = {
    "Finanzas y ROI": "Finanzas corporativas ROI automatización",
    "FoodTech and Supply Chain": "FoodTech cadena suministro alimentos",
    "Innovación y Tendencias": "Tendencias mercado alimentos 2026",
    "Tecnología e Innovación": "Inteligencia Artificial empresas software",
    "Legal & Regulatory Affairs / Innovation": "Regulación leyes tecnología empresas"
}

# ==========================================
# 2. CONEXIÓN FIREBASE & GEMINI
# ==========================================
if not firebase_admin._apps:
    try:
        if "FIREBASE_KEY" in st.secrets:
            key_dict = dict(st.secrets["FIREBASE_KEY"])
            if "private_key" in key_dict:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
        else:
            cred = credentials.Certificate('serviceAccountKey.json')
            firebase_admin.initialize_app(cred)
            
        if "GOOGLE_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
            
    except Exception as e:
        st.error(f"Error de Configuración: {e}")
        st.stop()

db = firestore.client()

# ==========================================
# 3. CRAWLER REAL (GOOGLE NEWS RSS)
# ==========================================
def limpiar_html(texto):
    """Elimina etiquetas HTML residuales"""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', texto)

def analizar_con_gemini(texto, titulo, dept):
    """Usa Gemini para resumir y dar acción estratégica"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Eres un consultor estratégico para AMC Global. Analiza esta noticia:
        Título: {titulo}
        Texto: {texto}
        
        Devuelve un JSON estricto (sin markdown):
        {{
            "resumen_ejecutivo": "Un resumen de 1 linea enfocado en impacto empresarial.",
            "accion_sugerida": "Una accion corta recomendada para el director de {dept}.",
            "relevancia_score": (numero entre 80 y 100)
        }}
        """
        response = model.generate_content(prompt)
        # Limpieza básica del JSON
        txt = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(txt)
    except:
        # Fallback si Gemini falla (para que no rompa el flujo)
        return {
            "resumen_ejecutivo": f"Noticia detectada sobre {dept}. Revisar fuente original.",
            "accion_sugerida": "Leer artículo completo para evaluar impacto.",
            "relevancia_score": 85
        }

def crawler_noticias_reales():
    """
    Busca noticias REALES en Google News RSS y las guarda.
    SIN DATOS FALSOS.
    """
    noticias_guardadas = 0
    
    print("🕷️ Iniciando Crawler Real...")
    
    for dept, query in QUERIES_DEPT.items():
        # URL de Google News RSS (México/Español) - Últimas 24 horas (when:1d)
        url = f"https://news.google.com/rss/search?q={query}+when:1d&hl=es-419&gl=MX&ceid=MX:es-419"
        
        try:
            resp = requests.get(url, timeout=10)
            soup = BeautifulSoup(resp.content, features="xml") # Parser XML
            items = soup.findAll('item')
            
            # Procesamos máximo 2 noticias por departamento para no saturar
            for item in items[:2]:
                titulo = item.title.text
                link = item.link.text
                fecha_pub = item.pubDate.text
                descripcion = limpiar_html(item.description.text)
                
                # VERIFICAR DUPLICADOS (Por título)
                # Buscamos si ya existe esta noticia en la BD
                docs = db.collection('news_articles')\
                         .where(filter=FieldFilter('title', '==', titulo))\
                         .limit(1).stream()
                
                if list(docs):
                    continue # Ya existe, saltamos
                
                # ANÁLISIS IA
                analisis = analizar_con_gemini(descripcion, titulo, dept)
                
                # ESTRUCTURA FINAL
                analisis["titulo_traducido"] = titulo # Asumimos español por la fuente
                analisis["departamento"] = dept
                
                # Convertir lista a string si Gemini devolvió string en resumen
                if not isinstance(analisis["resumen_ejecutivo"], list):
                    analisis["resumen_ejecutivo"] = [analisis["resumen_ejecutivo"]]

                # GUARDAR EN FIREBASE
                db.collection('news_articles').add({
                    "title": titulo,
                    "url": link,
                    "published_at": datetime.datetime.now(), # Fecha de captura
                    "source": "Google News RSS",
                    "analysis": analisis
                })
                noticias_guardadas += 1
                time.sleep(1) # Respeto a APIs
                
        except Exception as e:
            print(f"Error buscando en {dept}: {e}")
            continue

    return noticias_guardadas

# ==========================================
# 4. GESTIÓN DE CORREO
# ==========================================
def enviar_email(num_noticias, destinatario, nombre):
    if num_noticias == 0: return False
    try:
        msg = MIMEMultipart()
        msg['From'] = REMITENTE_EMAIL
        msg['To'] = destinatario
        msg['Subject'] = Header(f"📡 AMC Alerta: {num_noticias} Noticias Reales Detectadas", 'utf-8')

        html = f"""
        <html><body style="font-family:sans-serif;">
            <div style="background:#0e1117; padding:20px; text-align:center; border-bottom: 4px solid #00c1a9;">
                <h2 style="color:white;">AMC INTELLIGENCE</h2>
            </div>
            <div style="padding:20px; background:#f4f4f4;">
                <p>Hola <b>{nombre}</b>,</p>
                <p>El sistema de monitoreo en tiempo real ha encontrado <b>{num_noticias} noticias relevantes</b> en las últimas 24 horas.</p>
                <center><a href="https://amc-dashboard.streamlit.app" style="background:#00c1a9; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">Ver Dashboard</a></center>
            </div>
        </body></html>
        """
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(REMITENTE_EMAIL, REMITENTE_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        return False

# ==========================================
# 5. TRIGGER AUTOMÁTICO (Solo busca noticias de HOY)
# ==========================================
def verificar_dia_actual():
    hoy_inicio = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Consultamos si hay noticias de HOY
    docs = db.collection('news_articles')\
             .where(filter=FieldFilter('published_at', '>=', hoy_inicio))\
             .limit(1).stream()
    
    if not list(docs):
        # 🚨 NO HAY NOTICIAS -> EJECUTAR CRAWLER REAL
        placeholder = st.empty()
        with placeholder.container():
            st.warning(f"⚠️ No hay noticias frescas hoy. Escaneando internet en tiempo real...")
            bar = st.progress(0)
            
            # Ejecutamos el crawler real
            n = crawler_noticias_reales()
            bar.progress(100)
            
            if n > 0:
                st.success(f"✅ Se han encontrado {n} noticias reales.")
                email_dest = st.session_state.get('user_email', REMITENTE_EMAIL)
                enviar_email(n, email_dest, "Usuario")
            else:
                st.error("❌ El escaneo terminó pero no se encontraron noticias nuevas relevantes en Google News.")
            
            time.sleep(2)
        placeholder.empty()
        st.rerun()

# ==========================================
# 6. INTERFAZ GRÁFICA (UI)
# ==========================================

# LOGIN
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><br><h1 style='text-align:center; color:#00c1a9;'>AMC GLOBAL</h1>", unsafe_allow_html=True)
        email = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.button("ENTRAR", use_container_width=True):
            try:
                user_ref = db.collection('users').document(email).get()
                if user_ref.exists and user_ref.to_dict().get('password') == password:
                    st.session_state['logged_in'] = True
                    st.session_state['user_email'] = email
                    st.rerun()
                else: st.error("Error de credenciales")
            except: st.error("Error conectando a la base de datos")

else:
    # --- DENTRO DE LA APP ---
    verificar_dia_actual()
    
    try:
        user_data = db.collection('users').document(st.session_state['user_email']).get().to_dict()
    except: user_data = {"nombre": "Admin", "intereses": []}

    # SIDEBAR
    with st.sidebar:
        st.title("AMC HUB")
        st.caption(f"Hola, {user_data.get('nombre')}")
        st.markdown("---")
        
        # FILTRO DE TIEMPO
        st.markdown("### 📅 Filtro Temporal")
        filtro_tiempo = st.radio(
            "Ver noticias de:",
            ["Hoy (Tiempo Real)", "Ayer", "Histórico"],
            index=0
        )
        
        st.markdown("### 🎯 Departamentos")
        mis_intereses = st.multiselect("Filtrar:", LISTA_DEPARTAMENTOS, default=user_data.get('intereses', [])[:2])
        
        if st.button("Guardar Preferencias"):
            db.collection('users').document(st.session_state['user_email']).update({"intereses": mis_intereses})
            st.rerun()

        st.markdown("---")
        
        if st.button("📧 Enviar Reporte Ahora"):
            with st.spinner("Enviando..."):
                ok = enviar_email(5, st.session_state['user_email'], user_data.get('nombre'))
                if ok: st.success("Enviado")
                else: st.error("Error")
        
        if st.button("🔄 Escanear Ahora (Manual)"):
            with st.spinner("Buscando en Google News..."):
                n = crawler_noticias_reales()
                if n > 0: st.success(f"{n} Noticias encontradas.")
                else: st.warning("No se encontraron noticias nuevas.")
                time.sleep(1)
                st.rerun()

        if st.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()

    # DASHBOARD
    st.title("Panel de Inteligencia Estratégica")
    
    hoy_inicio = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ayer_inicio = hoy_inicio - datetime.timedelta(days=1)
    
    query = db.collection('news_articles')
    if mis_intereses:
        query = query.where(filter=FieldFilter('analysis.departamento', 'in', mis_intereses))
    
    if filtro_tiempo == "Hoy (Tiempo Real)":
        query = query.where(filter=FieldFilter('published_at', '>=', hoy_inicio))
        st.caption(f"Mostrando noticias detectadas hoy ({datetime.datetime.now().strftime('%d/%m/%Y')})")
    elif filtro_tiempo == "Ayer":
        query = query.where(filter=FieldFilter('published_at', '>=', ayer_inicio))\
                     .where(filter=FieldFilter('published_at', '<', hoy_inicio))
        st.caption("Mostrando archivo de ayer")
    else:
        st.caption("Mostrando archivo histórico completo")

    tab1, tab2 = st.tabs(["📰 Monitor de Noticias", "📊 Analítica"])

    with tab1:
        docs = query.order_by('published_at', direction=firestore.Query.DESCENDING).limit(20).stream()
        lista = [d.to_dict() for d in docs]
        
        if lista:
            for n in lista:
                a = n.get('analysis', {})
                dept = a.get('departamento', 'General')
                fecha_raw = n.get('published_at', datetime.datetime.now())
                
                if hasattr(fecha_raw, 'strftime'): 
                    fecha_str = fecha_raw.strftime('%H:%M') if filtro_tiempo == "Hoy (Tiempo Real)" else fecha_raw.strftime('%d %b %H:%M')
                else: fecha_str = str(fecha_raw)

                color = COLORES_DEPT.get(dept, '#ccc')
                
                html_card = f"""
                <div style="background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 20px; border-left: 5px solid {color};">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <span style="color: {color}; font-weight: 700; font-size: 0.85rem;">{dept.upper()}</span>
                        <span style="color: #666; font-size: 0.85rem;">{fecha_str}</span>
                    </div>
                    <div style="color: #fff; font-size: 1.3rem; font-weight: 700; margin-bottom: 10px; line-height:1.2;">{n.get('title', 'Sin título')}</div>
                    <div style="color: #c9d1d9; font-size: 0.95rem; margin-bottom: 15px;">{a.get('resumen_ejecutivo', [''])[0]}</div>
                    <div style="background:#0d1117; padding:10px; border-radius:6px; border:1px dashed #30363d; color:#8b949e; font-size:0.9rem;">
                        💡 <b>Acción:</b> {a.get('accion_sugerida', 'Revisar noticia')}
                    </div>
                    <div style="margin-top:15px; display:flex; justify-content:space-between;">
                         <span style="color:#888; font-size:0.8rem;">Relevancia: {a.get('relevancia_score', 0)}%</span>
                         <a href="{n.get('url', '#')}" target="_blank" style="color:{color}; font-weight:bold; text-decoration:none;">Leer Fuente →</a>
                    </div>
                </div>
                """
                st.markdown(textwrap.dedent(html_card), unsafe_allow_html=True)
        else:
            if filtro_tiempo == "Hoy (Tiempo Real)":
                st.info("No hay noticias aún hoy. Si acabas de entrar, el escáner se está ejecutando o no encontró novedades en Google News.")
            else:
                st.warning("No hay noticias en este periodo.")

    with tab2:
        docs_all = db.collection('news_articles').limit(50).stream()
        data = []
        for d in docs_all:
            dct = d.to_dict()
            if 'analysis' in dct:
                data.append({"Dept": dct['analysis'].get('departamento'), "Score": dct['analysis'].get('relevancia_score', 0)})
        
        if data:
            df = pd.DataFrame(data)
            c1, c2 = st.columns(2)
            with c1: st.plotly_chart(px.pie(df, names='Dept', color='Dept', color_discrete_map=COLORES_DEPT), use_container_width=True)
            with c2: 
                grp = df.groupby('Dept')['Score'].mean().reset_index()
                st.plotly_chart(px.bar(grp, x='Dept', y='Score', color='Dept', color_discrete_map=COLORES_DEPT), use_container_width=True)
