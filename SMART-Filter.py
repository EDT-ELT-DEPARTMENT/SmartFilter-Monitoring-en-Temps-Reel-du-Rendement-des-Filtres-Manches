import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import pandas as pd
import io

# Configuration de la page
st.set_page_config(
    page_title="SmartFilter Monitor - Dualité Électrostatique",
    layout="wide"
)

# En-tête réglementaire de la plateforme
st.title("SmartFilter Monitor")
st.subheader("Plateforme de gestion des EDTs-S2-2026-Département d'Électrotechnique-Faculté de génie électrique-UDL-SBA")
st.markdown("### ⚡ Analyseur Différentiel Charge de Carcasse (Masse) vs Induction (Faraday)")

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
        
        # Caractéristiques de l'étage de mesure
        self.capacite_faraday = 19.33e-12 # 19.33 pF
        self.r_shunt = 2.5e6              # 2.5 MOhms (Conditionnement d'amplitude)
        
        # Profils de bruit distincts (La carcasse subit la pollution CEM de l'usine)
        self.noise_carcasse_base = 0.5    # Bruit thermique de masse
        self.noise_carcasse_cem = 9.5     # Forts parasites VFD moteurs sur la masse de la carcasse
        self.noise_faraday_nA = 0.12      # Cage de Faraday blindée immunisée

        self.alpha = 0.15                 # Filtre EMA

    def generate_data_point(self, t, is_mechanically_damaged, temperature, cem_parasite_active):
        q_sec = self.debit_air_nominal / 3600.0 # Débit en m3/s (125 m3/s)
        
        # Correction du bug de variable ici : thermal_damage devient t_damage
        t_damage = temperature > self.t_critique_tissu
        if is_mechanically_damaged or t_damage: 
            current_eff = 0.978  
        else:
            current_eff = self.nominal_efficiency
         
        c_in = max(0.0, np.random.normal(self.base_concentration, 40.0))
        c_out = c_in * (1.0 - current_eff)
        masse_fuite_sec = (c_out * q_sec) / 1000.0  # Fuite particulaire en g/s
         
        # Triboélectricité en fonction de la température
        facteur_temperature = np.sqrt((temperature + 273.15) / 293.15)
        charge_specifique = self.k_tribo_base * facteur_temperature
        
        # Courant absolu généré par la séparation de charge
        i_généré_abs = masse_fuite_sec * charge_specifique

        # DUALITÉ PHYSIQUE :
        # 1. Carcasse = Drainage des électrons excédentaires (charges négatives accumulées)
        bruit_c = self.noise_carcasse_cem if cem_parasite_active else self.noise_carcasse_base
        raw_carcasse_neg = - (i_généré_abs + np.random.normal(0.0, bruit_c))

        # 2. Cage de Faraday = Induction sans contact du flux de poussière positive
        raw_faraday_pos = (i_généré_abs + np.random.normal(0.0, self.noise_faraday_nA))
         
        return raw_carcasse_neg, raw_faraday_pos, current_eff, t_damage, q_sec, masse_fuite_sec

sim = CementFilterFaradaySimulation()

# Navigation par onglets
tab1, tab2 = st.tabs(["📊 Suivi Simultané des Deux Paramètres", "🔬 Schéma du Bilan Électrique"])

# ==========================================
# ONGLET 1 : AFFICHAGE SIMULTANÉ DES PARAMÈTRES
# ==========================================
with tab1:
    st.sidebar.header("Paramètres Opérationnels")
    run_simulation = st.sidebar.toggle("Activer les acquisitions", value=True)
     
    st.sidebar.markdown("---")
    st.sidebar.subheader("Contrôle du Procédé")
    gas_temp = st.sidebar.slider("Température Processus (°C)", 120, 280, 200)
    trigger_mechanical = st.sidebar.toggle("Générer déchirure de manche", value=False)
    trigger_cem_noise = st.sidebar.toggle("Activer couplage CEM sur masse", value=True)
    speed = st.sidebar.slider("Période d'échantillonnage (s)", 0.1, 1.0, 0.3)

    # Initialisation des états de session
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
    if 'efficiencies_calculated' not in st.session_state:
        st.session_state.efficiencies_calculated = []
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 0
    if 'ema_carcasse_state' not in st.session_state:
        st.session_state.ema_carcasse_state = None
    if 'ema_faraday_state' not in st.session_state:
        st.session_state.ema_faraday_state = None

    placeholder = st.empty()

    if run_simulation:
        while True:
            t = st.session_state.current_step
            r_carcasse, r_faraday, true_eff, t_damage, q_sec, m_fuite_sec = sim.generate_data_point(
                t, trigger_mechanical, gas_temp, trigger_cem_noise
            )
             
            # Filtrage Numérique (EMA)
            if st.session_state.ema_carcasse_state is None:
                st.session_state.ema_carcasse_state = r_carcasse
            else:
                st.session_state.ema_carcasse_state = (sim.alpha * r_carcasse) + ((1.0 - sim.alpha) * st.session_state.ema_carcasse_state)
             
            if st.session_state.ema_faraday_state is None:
                st.session_state.ema_faraday_state = r_faraday
            else:
                st.session_state.ema_faraday_state = (sim.alpha * r_faraday) + ((1.0 - sim.alpha) * st.session_state.ema_faraday_state)
             
            # Conversion de tension vraie sur la cage de Faraday (Signal Positif)
            v_real_faraday = (st.session_state.ema_faraday_state * 1e-9) * sim.r_shunt
            
            # Calcul de l'efficacité estimée via l'induction positive
            facteur_t = np.sqrt((gas_temp + 273.15) / 293.15)
            i_max_theorique = ((sim.base_concentration * q_sec) / 1000.0) * (sim.k_tribo_base * facteur_t)
            estimated_eff = 1.0 - (st.session_state.ema_faraday_state / i_max_theorique)
            
            # Sauvegarde dans les registres glissants
            st.session_state.time_steps.append(t)
            st.session_state.raw_carcasse.append(r_carcasse)
            st.session_state.filtered_carcasse.append(st.session_state.ema_carcasse_state)
            st.session_state.raw_faraday.append(r_faraday)
            st.session_state.filtered_faraday.append(st.session_state.ema_faraday_state)
            st.session_state.voltage_faraday.append(v_real_faraday)
            st.session_state.efficiencies_calculated.append(estimated_eff * 100.0)
             
            if len(st.session_state.time_steps) > 80:
                st.session_state.time_steps.pop(0)
                st.session_state.raw_carcasse.pop(0)
                st.session_state.filtered_carcasse.pop(0)
                st.session_state.raw_faraday.pop(0)
                st.session_state.filtered_faraday.pop(0)
                st.session_state.voltage_faraday.pop(0)
                st.session_state.efficiencies_calculated.pop(0)
                 
            # --- CONFIGURATION DES PLOTS SIMULTANÉS ---
            fig = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.12,
                subplot_titles=(
                    "📈 Dynamique des Signaux Électriques Parallèles (Polarités Réelles)", 
                    "📊 Évolution du Rendement Global Déduit par Induction"
                )
            )
            
            # Paramètre 1 : Drainage Carcasse (Charges Négatives)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_carcasse),
                                     name="Courant Carcasse (Drainage -)", line=dict(color='#e67e22', width=2)), row=1, col=1)
            
            # Paramètre 2 : Cage de Faraday (Induction +)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_faraday),
                                     name="Courant Cage Faraday (Induction +)", line=dict(color='#2980b9', width=2.5)), row=1, col=1)
            
            # Rendement
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.efficiencies_calculated),
                                     name="Rendement Électrostatique (%)", line=dict(color='#2ecc71', width=2)), row=2, col=1)
            
            fig.update_layout(height=650, margin=dict(l=30, r=30, t=40, b=10))
            fig.update_yaxes(title_text="Courants (nA)", row=1, col=1)
            fig.update_yaxes(title_text="Rendement (%)", row=2, col=1)
            
            with placeholder.container():
                # Diagnostics d'États
                delta_verification = abs(abs(st.session_state.ema_carcasse_state) - st.session_state.ema_faraday_state)
                if t_damage:
                    st.error(f"🚨 EXTRUSION THERMIQUE CRITIQUE : Gaz à {gas_temp}°C > Seuil de rupture des mailles P84 (240°C).")
                elif delta_verification > 5.0 and trigger_cem_noise:
                    st.warning(f"⚡ ALERTE DISCORDANCE DE POLARITÉ : Écart de masse de {delta_verification:.2f} nA détecté. Des parasites induits perturbent la masse de la carcasse, mais la cage de Faraday reste isolée et stable.")
                elif estimated_eff < 0.992:
                    st.error(f"📉 FUITE CONFIRMÉE : Hausse corrélée sur le flux d'induction positif. Rendement bas : {estimated_eff*100:.3f}%")
                else:
                    st.success("✅ COMPORTEMENT NOMINAL : Cohérence parfaite entre drainage de masse et induction dynamique.")

                # AFFICHAGE SIMULTANÉ VIA DES COLONNES DE METRICS COMPLÈTES
                st.markdown("#### ⚙️ Comparatif Temps Réel des Deux Flux de Charge")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        label="🔏 Courant Carcasse (Drainage -)",
                        value=f"{st.session_state.ema_carcasse_state:.2f} nA",
                        delta="Évacuation vers Masse",
                        delta_color="inverse"
                    )
                with col2:
                    st.metric(
                        label="🌐 Courant Faraday (Induction +)",
                        value=f"{st.session_state.ema_faraday_state:.2f} nA",
                        delta="Induction Particulaire"
                    )
                with col3:
                    st.metric(
                        label="🔌 Tension Shunt Cage",
                        value=f"{v_real_faraday:.3f} V",
                        delta="Signal Échantillonné"
                    )
                with col4:
                    st.metric(
                        label="📈 Rendement Filtrage",
                        value=f"{estimated_eff * 100.0:.3f} %",
                        delta=f"{m_fuite_sec*1000:.1f} mg/s de fuite"
                    )
                
                st.plotly_chart(fig, use_container_width=True)
                
            st.session_state.current_step += 1
            time.sleep(speed)
    else:
        st.info("Système en attente. Veuillez basculer le commutateur latéral pour lancer la capture double pôle.")

# ==========================================
# ONGLET 2 : LOGIQUE DES FLUX ET EQUATIONS
# ==========================================
with tab2:
    st.header("Modélisation Avancée du Bilan Électrostatique")
    st.markdown("""
    En vertu de la **loi de conservation de la charge électrique**, le système implémenté met en évidence deux manifestations mesurables distinctes provenant d'un unique phénomène physique (l'électrisation triboélectrique dans le filtre) :
    """)
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("1. Courant de Drainage Carcasse ($I_{\\text{carc}}$)")
        st.markdown("> **Nature :** Évacuation conductive vers la prise de terre du filtre.")
        st.markdown("> **Signe :** Négatif (Accumulation stationnaire sur le média filtrant en polymère).")
        st.latex(r"I_{\text{carc}}(t) = - \left( \dot{m}_{\text{fuite}}(t) \cdot q_{\text{spécifique}} \right) + \xi_{\text{CEM}}(t)")
        st.caption("Remarque : Ce paramètre est sensible aux courants parasites de masse $\\xi_{\\text{CEM}}$ générés par les gros variateurs de vitesse de la cimenterie.")

    with col_b:
        st.subheader("2. Courant d'Induction Faraday ($I_{\\text{far}}$)")
        st.markdown("> **Nature :** Influence électrostatique sans contact à travers le cylindre intérieur.")
        st.markdown("> **Signe :** Positif (Transporté par le flux de particules de ciment en suspension).")
        st.latex(r"I_{\text{far}}(t) = + \left( \dot{m}_{\text{fuite}}(t) \cdot q_{\text{spécifique}} \right) + \xi_{\text{cage}}")
        st.caption("Remarque : Grâce au cylindre de garde externe de $\\varnothing 80\\text{ mm}$ relié à une masse propre, le bruit électromagnétique $\\xi_{\\text{cage}}$ est négligeable.")

    st.markdown("---")
    st.markdown("### Équation Finale Inter-paramètres")
    st.write("En l'absence de perturbations électromagnétiques industrielles sévères, la relation dynamique vérifie le théorème de neutralité :")
    st.latex(r"|I_{\text{Faraday}}(t)| - |I_{\text{Carcasse}}(t)| \approx 0")
    st.write("Toute divergence notable entre ces deux courbes (affichées en parallèle sur le graphique du premier onglet) permet de discriminer instantanément un problème de filtration réel d'un simple bruit de masse de l'usine.")
