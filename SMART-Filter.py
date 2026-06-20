import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import pandas as pd
import io
import datetime

# Configuration complète de la page de l'application
st.set_page_config(
    page_title="SmartFilter Monitor - Export Temporel",
    layout="wide"
)

# --- EN-TÊTE RÉGLEMENTAIRE ET RAPPEL DU TITRE EXIGÉ ---
st.title("SmartFilter Monitor")
st.subheader("Plateforme de gestion des EDTs-S2-2026-Département d'Électrotechnique-Faculté de génie électrique-UDL-SBA")
st.markdown("### ⚡ Analyseur Différentiel : Relevés Électrostatiques Temporels & Export Excel")

# --- COEUR DE MODÉLISATION PHYSIQUE BILATERALE ---
class CementFilterFaradaySimulation:
    def __init__(self):
        # Paramètres procédé - Cimenterie de Lafarge Oggaz
        self.base_concentration = 1200.0  # mg/m^3 (Concentration amont nominale)
        self.nominal_efficiency = 0.9995  # 99.95% de rendement nominal
        self.t_critique_tissu = 240.0     # °C (Seuil thermique P84)
        self.debit_air_nominal = 450000.0 # m^3/h

        # Constante triboélectrique intrinsèque du couple Ciment / P84
        self.k_tribo_base = 17684.0       # nC/g (Charge à saturation)
        
        # --- CARACTÉRISTIQUES GÉOMÉTRIQUES ET ÉLECTRIQUES DE LA CAGE ---
        self.longueur_L = 0.10            # Longueur utile (10 cm)
        self.diametre_int = 60.0          # Ø intérieur électrode de mesure en mm
        self.diametre_ext = 80.0          # Ø extérieur écran de blindage en mm
        self.capacite_faraday = 19.33e-12 # Capacité propre calculée (19.33 pF)
        self.r_shunt = 2.5e6              # Résistance de Shunt de conditionnement (2.5 MΩ)
        
        # Profils de bruit de fond
        self.noise_carcasse_base = 0.5    # Bruit thermique de masse
        self.noise_carcasse_cem = 9.5     # Parasites industriels (moteurs/variateurs) sur la carcasse
        self.noise_faraday_nA = 0.12      # Cage de Faraday blindée (haute immunité)

        self.alpha = 0.15                 # Coefficient de lissage (Filtre EMA)

    def generate_data_point(self, t, is_mechanically_damaged, temperature, cem_parasite_active):
        q_sec = self.debit_air_nominal / 3600.0 # Débit volumique en m3/s (125 m3/s)
        
        # Évaluation des défaillances thermiques ou mécaniques
        t_damage = temperature > self.t_critique_tissu
        if is_mechanically_damaged or t_damage: 
            current_eff = 0.978  
        else:
            current_eff = self.nominal_efficiency
         
        c_in = max(0.0, np.random.normal(self.base_concentration, 40.0))
        c_out = c_in * (1.0 - current_eff)
        masse_fuite_sec = (c_out * q_sec) / 1000.0  # Débit de fuite particulaire en g/s
         
        # Électrisation triboélectrique influencée par la température
        facteur_temperature = np.sqrt((temperature + 273.15) / 293.15)
        charge_specifique = self.k_tribo_base * facteur_temperature
        
        # Courant absolu généré par la séparation de charge
        i_généré_abs = masse_fuite_sec * charge_specifique

        # DUALITÉ PHYSIQUE DES POLARITÉS :
        # 1. Carcasse = Évacuation conductive des charges négatives accumulées sur le tissu
        bruit_c = self.noise_carcasse_cem if cem_parasite_active else self.noise_carcasse_base
        raw_carcasse_neg = - (i_généré_abs + np.random.normal(0.0, bruit_c))

        # 2. Cage de Faraday = Induction électrostatique sans contact du flux particulaire positif
        raw_faraday_pos = (i_généré_abs + np.random.normal(0.0, self.noise_faraday_nA))
         
        return raw_carcasse_neg, raw_faraday_pos, current_eff, t_damage, q_sec, masse_fuite_sec

# Instanciation du modèle de simulation
sim = CementFilterFaradaySimulation()

# --- INITIALISATION DES ÉTATS DE SESSION STREAMLIT ---
if 'time_steps' not in st.session_state:
    st.session_state.time_steps = []
if 'timestamps' not in st.session_state:
    st.session_state.timestamps = []  # Nouvelle banque de données pour stocker le temps réel
if 'raw_carcasse' not in st.session_state:
    st.session_state.raw_carcasse = []
if 'filtered_carcasse' not in st.session_state:
    st.session_state.filtered_carcasse = []
if 'raw_faraday' not in st.session_state:
    st.session_state.raw_faraday = []
if 'filtered_faraday' not in st.session_state:
    st.session_state.filtered_faraday = []
if 'voltage_faraday' not in st.session_state:
    st.session_state.voltage_faraday = []
if 'charge_acquise_pC' not in st.session_state:
    st.session_state.charge_acquise_pC = []
if 'efficiencies_calculated' not in st.session_state:
    st.session_state.efficiencies_calculated = []
if 'current_step' not in st.session_state:
    st.session_state.current_step = 0
if 'ema_carcasse_state' not in st.session_state:
    st.session_state.ema_carcasse_state = None
if 'ema_faraday_state' not in st.session_state:
    st.session_state.ema_faraday_state = None

# --- CONFIGURATION DU PANNEAU LATÉRAL (SIDEBAR) ---
st.sidebar.header("Paramètres Opérationnels")
run_simulation = st.sidebar.toggle("Activer l'acquisition en direct", value=True)

st.sidebar.markdown("---")
st.sidebar.subheader("📐 Spécifications Physiques du Capteur")

st.sidebar.markdown(fr"""
* **Longueur utile ($L$) :** {sim.longueur_L * 100:.1f} cm
* **Diamètre Intérieur ($\varnothing_{{int}}$) :** {sim.diametre_int:.1f} mm
* **Diamètre Extérieur ($\varnothing_{{ext}}$) :** {sim.diametre_ext:.1f} mm
* **Milieu Diélectrique :** Air sec ($\varepsilon_r \approx 1$)
* **Capacité de la Cage ($C_{{cage}}$) :** **{sim.capacite_faraday * 1e12:.2f} pF**
* **Résistance Shunt ($R_{{shunt}}$) :** {sim.r_shunt / 1e6:.1f} M$\Omega$
""")

st.sidebar.markdown("---")
st.sidebar.subheader("Contrôle du Procédé")
gas_temp = st.sidebar.slider("Température des Gaz (°C)", 120, 280, 200)
trigger_mechanical = st.sidebar.toggle("Simuler une déchirure de manche", value=False)
trigger_cem_noise = st.sidebar.toggle("Injecter des parasites CEM (Masse)", value=True)
speed = st.sidebar.slider("Intervalle d'échantillonnage (s)", 0.1, 1.0, 0.3)

# --- BLOC D'EXPORTATION EN FICHIER EXCEL (.XLSX) CALIBRÉ SUR LE TEMPS ---
st.sidebar.markdown("---")
st.sidebar.subheader("💾 Exportation des Données")

if len(st.session_state.timestamps) > 0:
    # Intégration de l'horodatage réel au lieu des simples index numériques
    data_dictionnaire = {
        "Horodatage (Temps Réel)": list(st.session_state.timestamps),
        "Courant de Carcasse Filtré (nA)": list(st.session_state.filtered_carcasse),
        "Tension mesurée au Shunt (V)": list(st.session_state.voltage_faraday),
        "Charge Électrostatique Acquise (pC)": list(st.session_state.charge_acquise_pC),
        "Rendement de Filtration Estimé (%)": list(st.session_state.efficiencies_calculated)
    }
    
    df_export = pd.DataFrame(data_dictionnaire)
    
    # Écriture binaire en mémoire tampon via IO
    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Données_Temporelles_EDT')
    
    processed_data = output_buffer.getvalue()
    
    st.sidebar.download_button(
        label="📥 Télécharger la table Excel (Série Temporelle)",
        data=processed_data,
        file_name="Chronologie_Cage_Faraday_EDT_2026.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.sidebar.info("En attente de relevés temporels pour compiler le tableur Excel.")

# Configuration des onglets de visualisation
tab1, tab2 = st.tabs(["📊 Tableau de Bord Temps Réel", "🔬 Rappels Théoriques & Formules"])

# ===================================================
# ONGLET 1 : AFFICHAGE DU TABLEAU DE BORD TEMPS RÉEL
# ===================================================
with tab1:
    placeholder = st.empty()

    if run_simulation:
        while True:
            t = st.session_state.current_step
            
            # Capturer l'instant exact avec millisecondes pour un suivi haute précision
            now_str = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            r_carcasse, r_faraday, true_eff, t_damage, q_sec, m_fuite_sec = sim.generate_data_point(
                t, trigger_mechanical, gas_temp, trigger_cem_noise
            )
             
            # Lissage numérique du courant négatif de carcasse (EMA)
            if st.session_state.ema_carcasse_state is None:
                st.session_state.ema_carcasse_state = r_carcasse
            else:
                st.session_state.ema_carcasse_state = (sim.alpha * r_carcasse) + ((1.0 - sim.alpha) * st.session_state.ema_carcasse_state)
             
            # Lissage numérique du courant de la cage de Faraday (Calcul interne masqué)
            if st.session_state.ema_faraday_state is None:
                st.session_state.ema_faraday_state = r_faraday
            else:
                st.session_state.ema_faraday_state = (sim.alpha * r_faraday) + ((1.0 - sim.alpha) * st.session_state.ema_faraday_state)
             
            # --- CALCUL DES PARAMÈTRES ÉLECTRIQUES ---
            v_real_faraday =
