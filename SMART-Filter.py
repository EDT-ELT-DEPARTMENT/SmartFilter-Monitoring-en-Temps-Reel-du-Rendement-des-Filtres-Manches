import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import pandas as pd
import io

# Configuration complète de la page de l'application
st.set_page_config(
    page_title="SmartFilter Monitor - Version Corrigée",
    layout="wide"
)

# --- EN-TÊTE RÉGLEMENTAIRE ET RAPPEL DU TITRE EXIGÉ ---
st.title("SmartFilter Monitor")
st.subheader("Plateforme de gestion des EDTs-S2-2026-Département d'Électrotechnique-Faculté de génie électrique-UDL-SBA")
st.markdown("### ⚡ Analyseur Différentiel Haute Précision : Drainage, Induction et Charge Acquise")

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

# --- CONFIGURATION DU PANNEAU LATÉRAL (SIDEBAR) ---
st.sidebar.header("Paramètres Opérationnels")
run_simulation = st.sidebar.toggle("Activer l'acquisition en direct", value=True)

st.sidebar.markdown("---")
st.sidebar.subheader("📐 Spécifications Physiques du Capteur")

# Utilisation d'une chaîne brute (fr) et de symboles clairs pour éliminer les bugs d'affichage
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

# Configuration des onglets de visualisation
tab1, tab2 = st.tabs(["📊 Tableau de Bord Temps Réel", "🔬 Rappels Théoriques & Formules"])

# ===================================================
# ONGLET 1 : AFFICHAGE DU TABLEAU DE BORD TEMPS RÉEL
# ===================================================
with tab1:
    # Initialisation des banques de données temporelles dans la session Streamlit
    if 'time_steps' not in st.session_state:
        st.session_state.time_steps = []
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

    # Conteneur dynamique unique pour rafraîchir l'affichage sans scintillement
    placeholder = st.empty()

    if run_simulation:
        while True:
            t = st.session_state.current_step
            r_carcasse, r_faraday, true_eff, t_damage, q_sec, m_fuite_sec = sim.generate_data_point(
                t, trigger_mechanical, gas_temp, trigger_cem_noise
            )
             
            # Lissage numérique du courant négatif de carcasse (EMA)
            if st.session_state.ema_carcasse_state is None:
                st.session_state.ema_carcasse_state = r_carcasse
            else:
                st.session_state.ema_carcasse_state = (sim.alpha * r_carcasse) + ((1.0 - sim.alpha) * st.session_state.ema_carcasse_state)
             
            # Lissage numérique du courant positif de la cage de Faraday (EMA)
            if st.session_state.ema_faraday_state is None:
                st.session_state.ema_faraday_state = r_faraday
            else:
                st.session_state.ema_faraday_state = (sim.alpha * r_faraday) + ((1.0 - sim.alpha) * st.session_state.ema_faraday_state)
             
            # --- CALCUL DES PARAMÈTRES ÉLECTRIQUES CORRIGÉS ---
            # Tension mesurée aux bornes du Shunt (V = I * R)
            v_real_faraday = (st.session_state.ema_faraday_state * 1e-9) * sim.r_shunt
            
            # Charge instantanée acquise par induction : Q = C * V (exprimée en PicoCoulombs pC)
            q_inst_pC = (sim.capacite_faraday * v_real_faraday) * 1e12
            
            # Estimation du rendement de filtrage en comparant le flux d'induction au flux théorique max
            facteur_t = np.sqrt((gas_temp + 273.15) / 293.15)
            i_max_theorique = ((sim.base_concentration * q_sec) / 1000.0) * (sim.k_tribo_base * facteur_t)
            estimated_eff = 1.0 - (st.session_state.ema_faraday_state / i_max_theorique)
            
            # Remplissage des tableaux de l'historique glissant
            st.session_state.time_steps.append(t)
            st.session_state.raw_carcasse.append(r_carcasse)
            st.session_state.filtered_carcasse.append(st.session_state.ema_carcasse_state)
            st.session_state.raw_faraday.append(r_faraday)
            st.session_state.filtered_faraday.append(st.session_state.ema_faraday_state)
            st.session_state.voltage_faraday.append(v_real_faraday)
            st.session_state.charge_acquise_pC.append(q_inst_pC)
            st.session_state.efficiencies_calculated.append(estimated_eff * 100.0)
             
            # Fenêtre glissante limitée à 80 points pour garder une lecture fluide
            if len(st.session_state.time_steps) > 80:
                st.session_state.time_steps.pop(0)
                st.session_state.raw_carcasse.pop(0)
                st.session_state.filtered_carcasse.pop(0)
                st.session_state.raw_faraday.pop(0)
                st.session_state.filtered_faraday.pop(0)
                st.session_state.voltage_faraday.pop(0)
                st.session_state.charge_acquise_pC.pop(0)
                st.session_state.efficiencies_calculated.pop(0)
                 
            # --- ARCHITECTURE DES GRAPHIQUES PLOTLY ---
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.09,
                subplot_titles=(
                    "📈 Analyse Parallèle des Courants (Drainage de Carcasse vs Induction de Faraday)",
                    "⚛️ Dynamique de la Charge Électrostatique Réelle Acquise (Q)", 
                    "📊 Évolution du Rendement de Filtration Estimé (%)"
                )
            )
            
            # Graphe 1 : Les deux courants opposés affichés simultanément
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_carcasse),
                                     name="Courant Carcasse (Drainage -)", line=dict(color='#e67e22', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_faraday),
                                     name="Courant Faraday (Induction +)", line=dict(color='#2980b9', width=2.5)), row=1, col=1)
            
            # Graphe 2 : Charge acquise en pC
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.charge_acquise_pC),
                                     name="Charge Induite (Q)", line=dict(color='#9b59b6', width=2.5)), row=2, col=1)
            
            # Graphe 3 : Rendement global calculé
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.efficiencies_calculated),
                                     name="Rendement (%)", line=dict(color='#2ecc71', width=2)), row=3, col=1)
            
            fig.update_layout(height=780, margin=dict(l=30, r=30, t=40, b=10), showlegend=True)
            fig.update_yaxes(title_text="Courants (nA)", row=1, col=1)
            fig.update_yaxes(title_text="Charge Q (pC)", row=2, col=1)
            fig.update_yaxes(title_text="Rendement (%)", row=3, col=1)
            fig.update_xaxes(title_text="Temps (Échantillons)", row=3, col=1)
            
            # Rendu en temps réel dans le bloc principal
            with placeholder.container():
                delta_verification = abs(abs(st.session_state.ema_carcasse_state) - st.session_state.ema_faraday_state)
                
                if t_damage:
                    st.error(f"🚨 EXTRUSION THERMIQUE CRITIQUE : Température de {gas_temp}°C supérieure à la limite admissible des manches P84 (240°C).")
                elif delta_verification > 5.0 and trigger_cem_noise:
                    st.warning(f"⚡ PARASITES DE MASSE DÉTECTÉS (CEM) : Écart de {delta_verification:.2f} nA. La carcasse subit les bruits moteurs, mais la cage de Faraday reste immunisée et stable.")
                elif estimated_eff < 0.992:
                    st.error(f"📉 CHUTE DU RENDEMENT DE FILTRATION : Fuite détectée sur le flux d'induction positif. Rendement bas : {estimated_eff*100:.3f}%")
                else:
                    st.success("✅ ÉQUILIBRE ÉLECTROSTATIQUE RECONNU : Parfaite symétrie entre les charges évacuées (carcasse) et induites (Faraday).")

                # --- AFFICHAGE SYNOPTIQUE CLAIR DES PARAMÈTRES (5 COLONNES) ---
                st.markdown("#### 🎛️ Indicateurs d'Acquisition de l'Interface")
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric(
                        label="🔏 Courant de Carcasse",
                        value=f"{st.session_state.ema_carcasse_state:.2f} nA",
                        delta="Drainage négatif (-)",
                        delta_color="inverse"
                    )
                with col2:
                    st.metric(
                        label="🌐 Courant de Faraday",
                        value=f"{st.session_state.ema_faraday_state:.2f} nA",
                        delta="Induction positive (+)"
                    )
                with col3:
                    st.metric(
                        label="⚛️ Charge Acquise (Q)",
                        value=f"{q_inst_pC:.2f} pC",
                        delta="Charge cumulée"
                    )
                with col4:
                    st.metric(
                        label="🔌 Tension du Shunt",
                        value=f"{v_real_faraday:.3f} V",
                        delta=f"Mesure sur {sim.r_shunt/1e6:.1f} MΩ"
                    )
                with col5:
                    st.metric(
                        label="📈 Rendement de Filtration",
                        value=f"{estimated_eff * 100.0:.3f} %",
                        delta=f"{m_fuite_sec*1000:.1f} mg/s de fuite",
                        delta_color="inverse" if estimated_eff < 0.995 else "normal"
                    )
                
                st.plotly_chart(fig, use_container_width=True)
                
            st.session_state.current_step += 1
            time.sleep(speed)
    else:
        st.info("⏸️ Système en attente d'acquisition. Activez le commutateur dans le volet latéral gauche pour lancer les captures.")

# ===================================================
# ONGLET 2 : RAPPELS THEORIQUES ET EQUATIONS MATRICIELLES
# ===================================================
with tab2:
    st.header("Validation Électrotechnique du Capteur Cylindrique")
    
    st.markdown("### 📐 Équation de Dimensionnement Fondamentale")
    st.write("La capacité géométrique d'une cage de Faraday coaxiale parfaite s'exprime par la relation de Gauss :")
    st.latex(r"C_{\text{cage}} = \frac{2 \pi \cdot \varepsilon_0 \cdot \varepsilon_r \cdot L}{\ln\left(\frac{R_2}{R_1}\right)}")
    
    st.markdown(f"""
    **Application de vos dimensions physiques réelles :**
    * Longueur active du capteur ($L$) = **{sim.longueur_L:.2f} m** (soit 10 cm)
    * Rayon interne de l'électrode active ($R_1$) = **{sim.diametre_int/2:.1f} mm** (Diamètre de 60 mm)
    * Rayon externe de l'écran protecteur ($R_2$) = **{sim.diametre_ext/2:.1f} mm** (Diamètre de 80 mm)
    * Permittivité absolue de l'air sec ($\varepsilon_0 \cdot \varepsilon_r$) = **$8,854 \times 10^{{-12}}$ F/m**
    
    Le calcul donne la valeur fixe implémentée dans votre programme : **{sim.capacite_faraday * 1e12:.2f} pF**.
    """)
    
    st.markdown("---")
    st.subheader("🔬 Déduction de la Charge Électrostatique Cumulée ($Q$)")
    st.write("La charge instantanée acquise par influence électrostatique pure sur la paroi intérieure est liée à la tension mesurée par l'équation :")
    st.latex(r"Q_{\text{acquise}}(t) = C_{\text{cage}} \times V_{\text{shunt}}(t)")
    st.write("En remplaçant la tension par le produit du courant d'induction et de la résistance de conditionnement, on obtient la valeur directe affichée sur le tableau de bord :")
    st.latex(r"Q_{\text{acquise}}(t) = C_{\text{cage}} \times \left( I_{\text{Faraday}}(t) \times R_{\text{shunt}} \right)")
