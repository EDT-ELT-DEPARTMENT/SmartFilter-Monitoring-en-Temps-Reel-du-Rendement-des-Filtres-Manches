import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db
from streamlit_autorefresh import st_autorefresh
from fpdf import FPDF

# =================================================================
# 1. CONFIGURATION DE LA PAGE & TITRES OFFICIELS
# =================================================================
ST_TITRE_OFFICIEL = "Plateforme de monitoring à distance de traitemet de déchets hospitaliers DASRI-EPH de Sidi Bel Abbès"
ADMIN_REF = "Plateforme de monitoring à distance de traitemet de dechets hospitaliers DASRI-EPH de Sidi Bel Abbès"

st.set_page_config(
    page_title=ST_TITRE_OFFICIEL,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Rafraîchissement automatique toutes les 2 secondes
st_autorefresh(interval=2000, key="datarefresh")

# Initialisation persistante du décalage (Offset) pour le calibrage "Zéro"
if 'nox_offset' not in st.session_state:
    st.session_state.nox_offset = 0.0

# Navigation par menu latéral
st.sidebar.title("📂 Menu Principal")
page = st.sidebar.radio("Navigation :", ["📊 Monitoring Temps Réel", "🔬 Prototype & Datasheet"])

# =================================================================
# 2. FONCTIONS DE SERVICE (FIREBASE & PDF)
# =================================================================
@st.cache_resource
def initialiser_firebase():
    """Initialise la connexion Firebase de manière sécurisée"""
    try:
        if not firebase_admin._apps:
            if "firebase" in st.secrets:
                fb_secrets = dict(st.secrets["firebase"])
                if "private_key" in fb_secrets:
                    fb_secrets["private_key"] = fb_secrets["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(fb_secrets)
            else:
                cred = credentials.Certificate("votre-cle.json")
                
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://oh-generator-plasma-sba-default-rtdb.europe-west1.firebasedatabase.app'
            })
        return True
    except Exception as e:
        st.sidebar.error(f"Erreur de liaison Cloud : {e}")
        return False

def generer_pdf_datasheet():
    """Génère l'export PDF de la fiche technique"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, txt="DATASHEET TECHNIQUE DU PROTOTYPE HYBRIDE", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", size=11)
    pdf.cell(190, 10, txt=f"Projet : {ST_TITRE_OFFICIEL}", ln=True)
    pdf.cell(190, 10, txt=f"Référence : {ADMIN_REF}", ln=True)
    pdf.cell(190, 10, txt=f"Date de génération : {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True)
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(190, 10, txt="1. Architecture du Système", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(190, 8, txt="Ce prototype utilise des générateurs d'ozone et un réacteur DBD "
                               "pour la production de radicaux hydroxyles destinés à la "
                               "neutralisation des agents pathogènes hospitaliers.")
    return pdf.output(dest='S').encode('latin-1')

# =================================================================
# 3. PAGE 1 : MONITORING TEMPS RÉEL
# =================================================================
if page == "📊 Monitoring Temps Réel":
    st.title("⚡ Monitoring des Oxydants Hybrides")
    st.markdown(f"### {ST_TITRE_OFFICIEL}")
    st.info(f"📅 État du système au : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    # Initialisation des états
    if 'temp_reelle' not in st.session_state: st.session_state.temp_reelle = 25.0
    if 'hum_reelle' not in st.session_state: st.session_state.hum_reelle = 50.0
    if 'co_reelle' not in st.session_state: st.session_state.co_reelle = 0.0
    if 'h2_reelle' not in st.session_state: st.session_state.h2_reelle = 0.0
    if 'nox_reelle' not in st.session_state: st.session_state.nox_reelle = 0.0

    with st.sidebar:
        st.header("🎮 Contrôle & Réception")
        mode_experimental = st.toggle("🚀 Activer Flux Réel (Wemos/TTGO)", value=True)
        st.divider()
        
        if mode_experimental:
            carte_active = st.selectbox("📡 Source de données :", ["Wemos D1 Mini", "TTGO ESP32"])
            fb_path = "/EDT_SBA" if "Wemos" in carte_active else "/EDT_SBA/TTGOESP32"
            
            if initialiser_firebase():
                try:
                    ref = db.reference(fb_path)
                    data_cloud = ref.get()
                    if data_cloud:
                        st.session_state.temp_reelle = float(data_cloud.get('temperature', 25.0))
                        st.session_state.hum_reelle = float(data_cloud.get('humidite', 50.0))
                        
                        # Récupération NOx Entrant (MQ-135 à la sortie de l'incinérateur)
                        val_nox = int(data_cloud.get('nox', 0))
                        if val_nox > 0:
                            ratio = (1023.0 / val_nox) - 1.0
                            st.session_state.nox_reelle = round(116.6 * pow(ratio, -2.76), 2)
                        
                        st.session_state.co_reelle = float(data_cloud.get('co', 0.0))
                        st.session_state.h2_reelle = float(data_cloud.get('h2', 0.0))
                        
                        st.success(f"✅ Flux Multi-Capteurs Actif")
                except Exception as e:
                    st.error(f"❌ Erreur : {e}")
            
            # --- SECTION CALIBRAGE ---
            st.subheader("⚖️ Calibrage du Capteur")
            if st.button("Calibrer le Zéro (Tare)"):
                st.session_state.nox_offset = st.session_state.nox_reelle
                st.success(f"Zéro fixé à {st.session_state.nox_offset} ppm")
            
            if st.button("Réinitialiser Calibrage"):
                st.session_state.nox_offset = 0.0
                st.info("Calibrage réinitialisé")

            st.divider()
            nb_gen = st.slider("Générateurs Actifs", 0, 3, 1)
            debit_aspiration = st.slider("Débit Aspirateur (m³/h)", 1.0, 15.0, 6.0)
        else:
            st.header("💻 Mode Simulation")
            st.session_state.temp_reelle = st.slider("Température T (°C)", 15.0, 80.0, 25.0)
            st.session_state.hum_reelle = st.slider("Humidité Relative H (%)", 5.0, 95.0, 50.0)
            st.session_state.nox_reelle = st.slider("Nox Brut (ppm)", 0.0, 500.0, 150.0)
            st.session_state.co_reelle = 15.0
            st.session_state.h2_reelle = 8.0
            debit_aspiration = 5.0
            nb_gen = 1

   # --- MOTEUR DE DÉDUCTION CHIMIQUE ---
    temp_actuelle = st.session_state.temp_reelle
    hum_actuelle = st.session_state.hum_reelle
    
    f_H = np.exp(-0.025 * (hum_actuelle - 10)) if hum_actuelle > 10 else 1.0
    f_T = np.exp(-0.030 * (temp_actuelle - 25)) if temp_actuelle > 25 else 1.0
    
    o3_ppm_in = (nb_gen * 120 * f_H * f_T) / debit_aspiration if debit_aspiration > 0 else 0
    oh_ppm_in = (nb_gen * 45 * (1 - f_H) * f_T) / debit_aspiration if debit_aspiration > 0 else 0

    # Application de la Tare (Calibrage) sur le NOx entrant
    nox_utile = max(0.0, st.session_state.nox_reelle - st.session_state.nox_offset)

    tau = 6.0 / debit_aspiration if debit_aspiration > 0 else 0 
    k_react = 0.12 
    
    potentiel_oxydant = (oh_ppm_in + o3_ppm_in * 0.4) 
    consommation = potentiel_oxydant * tau * k_react
    
    # --- LOGIQUE D'EFFICACITÉ AVEC SEUIL ---
    if nox_utile > 0.5:
        nox_sortant = max(nox_utile * 0.05, nox_utile - consommation)
        efficacite_calculée = (1 - (nox_sortant / nox_utile)) * 100
        txt_efficacite = f"{efficacite_calculée:.1f} %"
    else:
        nox_sortant = 0.0
        efficacite_calculée = 0.0
        txt_efficacite = "0.0% (Repos)"

    # --- AFFICHAGE MÉTRIQUES ---
    st.subheader(f"Statut : {'🔴 MESURE RÉELLE' if mode_experimental else '🔵 SIMULATION'}")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🌡️ Température", f"{temp_actuelle:.1f} °C")
    m2.metric("💧 Humidité", f"{hum_actuelle:.1f} %")
    m3.metric("🧪 Monoxyde CO", f"{st.session_state.co_reelle:.1f} ppm")
    m4.metric("🔋 Hydrogène H2", f"{st.session_state.h2_reelle:.1f} ppm")

    st.markdown("#### 🧪 Analyse de la Neutralisation Chimique")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🌀 Ozone (O3)", f"{o3_ppm_in:.2f} ppm", delta="Oxydant")
    c2.metric("✨ Hydroxyle (·OH)", f"{oh_ppm_in:.2f} ppm", delta="Radicalaire")
    
    # Affichage du NOx avec le delta du brut pour voir l'effet du Tare
    c3.metric("⚠️ NOx sortie incinérateur", f"{nox_utile:.1f} ppm", delta=f"Brut: {st.session_state.nox_reelle}")
    
    # Affichage de l'efficacité avec le texte dynamique (Repos ou Valeur)
    c4.metric("🎯 Efficacité Déduite", txt_efficacite)

    st.divider()
    
    # --- GRAPHIQUE INTERACTIF DE CINÉTIQUE ---
    q_range = np.linspace(1, 20, 100)
    y_vals_oh = [(nb_gen * 45 * (1 - f_H) * f_T) / q for q in q_range]
    y_vals_o3 = [(nb_gen * 120 * f_H * f_T) / q for q in q_range]
    
    y_vals_nox_out = []
    for q in q_range:
        t_q = 6.0 / q
        oh_q = (nb_gen * 45 * (1 - f_H) * f_T) / q
        o3_q = (nb_gen * 120 * f_H * f_T) / q
        cons_q = (oh_q + o3_q * 0.4) * t_q * k_react
        y_vals_nox_out.append(max(nox_utile * 0.05, nox_utile - cons_q))

    fig_q = go.Figure()
    fig_q.add_trace(go.Scatter(x=q_range, y=y_vals_oh, name="Potentiel ·OH", line=dict(color='orange', width=2)))
    fig_q.add_trace(go.Scatter(x=q_range, y=y_vals_o3, name="Potentiel O3", line=dict(color='cyan', width=1, dash='dash')))
    fig_q.add_trace(go.Scatter(x=q_range, y=y_vals_nox_out, name="NOx Sortant (Déduit)", line=dict(color='red', width=4)))

    fig_q.update_layout(
        template="plotly_dark", 
        title="Cinétique de Réaction : Déduction du NOx de sortie selon le débit", 
        xaxis_title="Débit Q (m³/h)", 
        yaxis_title="Concentration (ppm)",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )
    st.plotly_chart(fig_q, use_container_width=True)

    # --- RAPPORT DE PERFORMANCE ---
    st.subheader("📊 Rapport de Traitement DASRI")
    col_rep1, col_rep2, col_rep3 = st.columns(3)
    
    with col_rep1:
        st.metric("📉 NOx Neutralisés", f"{(nox_utile - nox_sortant):.1f} ppm")
    
    with col_rep2:
        temps_s = 3.6 / debit_aspiration if debit_aspiration > 0 else 0
        st.metric("⏳ Temps de séjour réel", f"{temps_s:.2f} s")
        
    with col_rep3:
        st.metric("📤 Rejet Final (Sortie)", f"{nox_sortant:.1f} ppm")

    st.info(f"💡 **Analyse DASRI :** Offset de calibrage actuel : {st.session_state.nox_offset} ppm. Le traitement réduit la charge utile de {efficacite_calculée:.1f}%.")

# =================================================================
# 4. PAGE 2 : PROTOTYPE & DATASHEET
# =================================================================
elif page == "🔬 Prototype & Datasheet":
    st.title("🔬 Architecture & Spécifications")
    st.markdown(f"#### {ST_TITRE_OFFICIEL}")
    st.divider()

    col_img, col_desc = st.columns([1.6, 1])
    with col_img:
        st.subheader("🖼️ Vue du Prototype")
        try:
            st.image("prototype.jpg", caption="Unité Hybride de traitement des effluents gazeux DASRI.", use_container_width=True)
        except:
            st.error("⚠️ Image 'prototype.jpg' non trouvée.")

    with col_desc:
        st.subheader("📝 Documentation Technique")
        st.success("**Principe :** La neutralisation s'effectue par oxydation radicalaire avancée dans une chambre de séjour à débit contrôlé.")
        try:
            pdf_data = generer_pdf_datasheet()
            st.download_button("📥 Télécharger la Datasheet (PDF)", pdf_data, "Fiche_Technique_DASRI_SBA.pdf", "application/pdf")
        except: pass

    st.divider()
    st.subheader("📐 Architecture & Nomenclature des Composants")

    data_tab = {
        "Bloc/Fonction": ["Filtration Électrostatique", "Ionisation Diélectrique", "Analyse de Combustion (CO)", "Analyse des Rejets (NOx)", "Hygrométrie & Température", "Supervision & IHM"],
        "Code (Référence)": ["ESP-MOD-01", "DBD-RECT-150", "MQ-9-SENS", "MQ-135-SENS", "DHT22-DIGITAL", "TTGO-T-POE-V1"],
        "Mode et plage de fonctionnement": ["Continu", "15-25 kHz", "10-1000 ppm", "Multi-gaz", "-40 à 80°C", "Dual-Core"],
        "Temps de traitement": ["24h/24", "Cycle Traitement", "Réel", "Permanent", "Échantillonnage 2s", "Cloud Sync"],
        "Localisation": ["Ligne 1", "Ligne 2", "Chambre Combustion", "Sortie Aspirateur", "Chambre de Réaction", "Pupitre"],
        "Type de fonctionnement": ["Haute Tension", "Plasma Froid", "Analogique", "Analogique", "Numérique", "IoT"]
    }
    st.table(pd.DataFrame(data_tab))

# =================================================================
# 5. PIED DE PAGE
# =================================================================
st.warning("⚠️ Sécurité : Risque de Haute Tension (35kV). Surveillance active du process DASRI-EPH.")
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown(f"<center><b>{ST_TITRE_OFFICIEL}</b><br><small>{ADMIN_REF}</small></center>", unsafe_allow_html=True)


