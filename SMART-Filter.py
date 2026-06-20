import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import pandas as pd
import io

# Configuration de la page
st.set_page_config(
    page_title="SmartFilter Monitor - Cage de Faraday Unique",
    layout="wide"
)

# En-tête réglementaire de la plateforme
st.title("SmartFilter Monitor")
st.subheader("Plateforme de gestion des EDTs-S2-2026-Département d'Électrotechnique-Faculté de génie électrique-UDL-SBA")
st.markdown("**Supervision Électrostatique Exclusive par Cage de Faraday Coaxiale et Courant de Carcasse**")

# --- COEUR DE MODÉLISATION PHYSIQUE EXCLUSIVE ---
class CementFilterFaradaySimulation:
    def __init__(self):
        # Paramètres procédé - Cimenterie de Lafarge Oggaz
        self.base_concentration = 1200.0  # mg/m^3 (Concentration amont nominale)
        self.nominal_efficiency = 0.9995  # 99.95% de rendement de filtration nominal
        self.t_critique_tissu = 240.0     # °C (Seuil thermique des manches P84)
        self.debit_air_nominal = 450000.0 # m^3/h

        # Constante triboélectrique intrinsèque du couple Ciment / P84
        self.k_tribo_base = 17684.0       # nC/g (Charge à saturation)
        
        # Caractéristiques réelles de votre cage de Faraday (L=10cm, D_ext=80mm, D_int=60mm)
        self.capacite_faraday = 19.33e-12 # Farads (19.33 pF)
        
        # Bruits de mesure et environnement électromagnétique (CEM)
        self.noise_faraday_nA = 0.12      # Bruit ultra-faible grâce au blindage externe de 80mm
        self.noise_carcasse_base = 0.4    # Bruit résiduel de masse
        self.noise_carcasse_cem = 8.8     # Parasites massifs induits par les variateurs moteurs (VFD)

        self.alpha = 0.15                 # Coefficient du filtre numérique EMA

    def generate_data_point(self, t, is_mechanically_damaged, temperature, cem_parasite_active):
        # 1. Calcul du débit d'air instantané en m3/s
        q_sec = self.debit_air_nominal / 3600.0 # 125 m3/s
        
        # 2. Modélisation des défaillances des manches (thermique ou mécanique)
        thermal_damage = temperature > self.t_critique_tissu
        if is_mechanically_damaged or thermal_damage:
            current_eff = 0.978  # Chute du rendement à 97.8% en cas de fuite ou déchirure
        else:
            current_eff = self.nominal_efficiency
         
        # 3. Évolution des concentrations de poussière
        c_in = max(0.0, np.random.normal(self.base_concentration, 40.0))
        c_out = c_in * (1.0 - current_eff)
        
        # 4. Débit massique particulaire résiduel (en g/s)
        masse_fuite_sec = (c_out * q_sec) / 1000.0
         
        # 5. Calcul du coefficient thermique de transfert de charge
        facteur_temperature = np.sqrt((temperature + 273.15) / 293.15)
        charge_specifique = self.k_tribo_base * facteur_temperature
        
        # 6. Déduction du courant théorique induit (I = dQ/dt)
        # Masse (g/s) * Charge (nC/g) = Courant en nA
        i_fuite_theorique = masse_fuite_sec * charge_specifique

        # --- SIGNAL DE CARCASSE (Drainage des électrons négatifs via les fils conducteurs) ---
        bruit_carcasse = self.noise_carcasse_cem if cem_parasite_active else self.noise_carcasse_base
        raw_carcasse = max(0.0, i_fuite_theorique + np.random.normal(0.0, bruit_carcasse))

        # --- SIGNAL DE LA CAGE DE FARADAY (Induction des charges positives en cheminée) ---
        raw_faraday = max(0.0, i_fuite_theorique + np.random.normal(0.0, self.noise_faraday_nA))
         
        return raw_carcasse, raw_faraday, current_eff, thermal_damage, q_sec, masse_fuite_sec

# Instanciation
sim = CementFilterFaradaySimulation()

# --- ONGLETS RESTRUCTURÉS ---
tab1, tab2 = st.tabs(["📊 Diagnostic Électrostatique Cage", "🔬 Équations Fondamentales"])

# ==========================================
# ONGLET 1 : SUPERVISION EXCLUSIVE DU PROCÉDÉ
# ==========================================
with tab1:
    st.sidebar.header("Paramètres Opérationnels")
    run_simulation = st.sidebar.toggle("Démarrer la supervision", value=True)
     
    st.sidebar.markdown("---")
    st.sidebar.subheader("Contrôle du Flux Cimenterie")
    gas_temp = st.sidebar.slider("Température des fumées (°C)", 120, 280, 210)
    trigger_mechanical = st.sidebar.toggle("Simuler une déchirure physique", value=False)
    trigger_cem_noise = st.sidebar.toggle("Injecter parasites CEM (Variateurs)", value=True)
    speed = st.sidebar.slider("Cadence d'acquisition (s)", 0.1, 1.0, 0.3)

    # --- SESSIONS TEMPORELLES ET EXTRACTION ---
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
    if 'charge_faraday_pC' not in st.session_state:
        st.session_state.charge_faraday_pC = []
    if 'voltage_faraday' not in st.session_state:
        st.session_state.voltage_faraday = []
    if 'delta_i_differential' not in st.session_state:
        st.session_state.delta_i_differential = []
    if 'efficiencies_calculated' not in st.session_state:
        st.session_state.efficiencies_calculated = []
    if 'instantaneous_mass_flow' not in st.session_state:
        st.session_state.instantaneous_mass_flow = []
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 0
    if 'ema_carcasse_state' not in st.session_state:
        st.session_state.ema_carcasse_state = None
    if 'ema_faraday_state' not in st.session_state:
        st.session_state.ema_faraday_state = None

    st.sidebar.markdown("---")
    st.sidebar.subheader("🛠️ Données & Sauvegarde")

    if st.sidebar.button("Réinitialiser l'historique"):
        st.session_state.time_steps = []
        st.session_state.raw_carcasse = []
        st.session_state.filtered_carcasse = []
        st.session_state.raw_faraday = []
        st.session_state.filtered_faraday = []
        st.session_state.charge_faraday_pC = []
        st.session_state.voltage_faraday = []
        st.session_state.delta_i_differential = []
        st.session_state.efficiencies_calculated = []
        st.session_state.instantaneous_mass_flow = []
        st.session_state.current_step = 0
        st.session_state.ema_carcasse_state = None
        st.session_state.ema_faraday_state = None
        st.rerun()

    # --- EXPORTATION DES SIGNAUX NETTOYÉS ---
    lengths = [
        len(st.session_state.time_steps),
        len(st.session_state.raw_carcasse),
        len(st.session_state.filtered_carcasse),
        len(st.session_state.raw_faraday),
        len(st.session_state.filtered_faraday),
        len(st.session_state.voltage_faraday),
        len(st.session_state.delta_i_differential),
        len(st.session_state.efficiencies_calculated),
        len(st.session_state.instantaneous_mass_flow)
    ]
    min_len = min(lengths) if lengths else 0

    if min_len > 0:
        df_export = pd.DataFrame({
            "Temps (Index)": list(st.session_state.time_steps)[:min_len],
            "I_Carcasse Brut (nA)": list(st.session_state.raw_carcasse)[:min_len],
            "I_Carcasse Filtré (nA)": list(st.session_state.filtered_carcasse)[:min_len],
            "I_Faraday Brut (nA)": list(st.session_state.raw_faraday)[:min_len],
            "I_Faraday Filtré (nA)": list(st.session_state.filtered_faraday)[:min_len],
            "Tension Cage de Faraday (V)": list(st.session_state.voltage_faraday)[:min_len],
            "Écart Électrique Delta_I (nA)": list(st.session_state.delta_i_differential)[:min_len],
            "Rendement Électrostatique (%)": list(st.session_state.efficiencies_calculated)[:min_len],
            "Débit Massique de Fuite (mg/s)": list(st.session_state.instantaneous_mass_flow)[:min_len]
        })
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name="Faraday_Exclusive_Data")
        excel_buffer.seek(0)
        
        st.sidebar.download_button(
            label="📥 Télécharger le registre d'induction (.xlsx)",
            data=excel_buffer,
            file_name="rapport_faraday_exclusif.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="excel_download"
        )
    else:
        st.sidebar.caption("⏳ En attente de stabilisation des signaux...")

    placeholder = st.empty()

    if run_simulation:
        while True:
            t = st.session_state.current_step
            r_carcasse, r_faraday, true_eff, t_damage, q_sec, m_fuite_sec = sim.generate_data_point(
                t, trigger_mechanical, gas_temp, trigger_cem_noise
            )
             
            # Filtrage numérique exponentiel (EMA) - Ligne Carcasse
            if st.session_state.ema_carcasse_state is None:
                st.session_state.ema_carcasse_state = r_carcasse
            else:
                st.session_state.ema_carcasse_state = (sim.alpha * r_carcasse) + ((1.0 - sim.alpha) * st.session_state.ema_carcasse_state)
             
            # Filtrage numérique exponentiel (EMA) - Cage de Faraday
            if st.session_state.ema_faraday_state is None:
                st.session_state.ema_faraday_state = r_faraday
            else:
                st.session_state.ema_faraday_state = (sim.alpha * r_faraday) + ((1.0 - sim.alpha) * st.session_state.ema_faraday_state)
             
            # --- RELATION COURANT -> CHARGE -> TENSION COAXIALE ---
            # Fenêtre d'intégration d'acquisition équivalente de dt = 100 ms
            # Q (pC) = I (nA) * dt (ms)
            q_faraday_pC = st.session_state.ema_faraday_state * 100.0
            v_real_faraday = q_faraday_pC / 19.33  # V = Q_pC / C_pF
            
            # Évaluation différentielle en temps réel
            delta_i = abs(st.session_state.ema_carcasse_state - st.session_state.ema_faraday_state)
             
            # Calcul du rendement instantané par la cage de Faraday
            facteur_t = np.sqrt((gas_temp + 273.15) / 293.15)
            charge_specifique_actuelle = sim.k_tribo_base * facteur_t
            i_max_theorique = ((sim.base_concentration * q_sec) / 1000.0) * charge_specifique_actuelle
            estimated_eff_faraday = 1.0 - (st.session_state.ema_faraday_state / i_max_theorique)
            
            # Remplissage des registres (Fenêtre glissante stricte de 100 itérations)
            st.session_state.time_steps.append(t)
            st.session_state.raw_carcasse.append(r_carcasse)
            st.session_state.filtered_carcasse.append(st.session_state.ema_carcasse_state)
            st.session_state.raw_faraday.append(r_faraday)
            st.session_state.filtered_faraday.append(st.session_state.ema_faraday_state)
            st.session_state.charge_faraday_pC.append(q_faraday_pC)
            st.session_state.voltage_faraday.append(v_real_faraday)
            st.session_state.delta_i_differential.append(delta_i)
            st.session_state.efficiencies_calculated.append(estimated_eff_faraday * 100.0)
            st.session_state.instantaneous_mass_flow.append(m_fuite_sec * 1000.0) # conversion en mg/s
             
            if len(st.session_state.time_steps) > 100:
                st.session_state.time_steps.pop(0)
                st.session_state.raw_carcasse.pop(0)
                st.session_state.filtered_carcasse.pop(0)
                st.session_state.raw_faraday.pop(0)
                st.session_state.filtered_faraday.pop(0)
                st.session_state.charge_faraday_pC.pop(0)
                st.session_state.voltage_faraday.pop(0)
                st.session_state.delta_i_differential.pop(0)
                st.session_state.efficiencies_calculated.pop(0)
                st.session_state.instantaneous_mass_flow.pop(0)
                 
            # --- CONSTRUCTION DES GRAPHES SANS INSTRUMENT D'IMPACT ---
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.08,
                subplot_titles=(
                    "Bilan de Courant : Courant de drainage carcasse (I_carc) vs Courant d'induction Faraday (I_far)", 
                    "Dynamique de Tension de la Cage Coaxiale Réelle (V_cage calculée sur C = 19.33 pF)", 
                    "Rendement Électrostatique de Séparation Déduit (%)"
                )
            )
            
            # Graphe 1 : Courants d'équilibre (Carcasse vs Faraday)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.raw_carcasse),
                                     name="Carcasse : Brut", line=dict(color='rgba(230, 126, 34, 0.2)', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_carcasse),
                                     name="Carcasse : Filtré (I_carc)", line=dict(color='#e67e22', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.raw_faraday),
                                     name="Faraday : Brut", line=dict(color='rgba(52, 152, 219, 0.2)', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_faraday),
                                     name="Faraday : Filtré (I_far)", line=dict(color='#3498db', width=2.5)), row=1, col=1)
            
            # Graphe 2 : Tension calculée aux bornes de la cage de 19.33 pF
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.voltage_faraday),
                                     name="Tension d'influence (V_cage)", line=dict(color='#9b59b6', width=2.5)), row=2, col=1)
            
            # Graphe 3 : Rendement de captage déduit
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.efficiencies_calculated),
                                     name="Rendement Électrostatique", line=dict(color='#2ecc71', width=2.5)), row=3, col=1)
            fig.add_hline(y=99.2, line_dash="dash", line_color="red", annotation_text="Limite Rejet Seuil Bas (99.2%)", row=3, col=1)
             
            fig.update_layout(height=800, showlegend=True, margin=dict(l=20, r=20, t=30, b=10))
            fig.update_yaxes(title_text="Intensités (nA)", row=1, col=1)
            fig.update_yaxes(title_text="Tension (V)", row=2, col=1)
            fig.update_yaxes(title_text="Efficacité (%)", row=3, col=1)
            fig.update_xaxes(title_text="Temps (Itérations)", row=3, col=1)
             
            with placeholder.container():
                # Diagnostics automatiques basés sur la cage de Faraday
                if t_damage:
                    st.error(f"🚨 EXTRUSION THERMIQUE CRITIQUE : Gaz à {gas_temp}°C > Seuil de tenue du polymère P84 (240°C). Rupture des manches suspectée.")
                elif delta_i > 5.0 and trigger_cem_noise:
                    st.warning(f"⚡ DISCORDANCE CEM INDUSTRIELLE : Le bruit de masse affecte I_carcasse ($\Delta I$ = {delta_i:.2f} nA). La cage de Faraday reste stable et immunisée.")
                elif estimated_eff_faraday < 0.992:
                    st.error(f"📉 ANOMALIE DE FILTRATION CORRÉLÉE : La signature de la cage confirme une fuite massive de poussières. Rendement : {estimated_eff_faraday*100:.3f} %.")
                else:
                    st.success(f"✅ PROCÉDÉ SÉCURISÉ : Équilibre des charges parfait à {gas_temp}°C. Émission sous contrôle.")
                
                # PANNEAU NUMÉRIQUE - INTÉGRATION GÉNIE ÉLECTRIQUE
                st.markdown("### 🎛️ Paramètres Électrostatiques Centrés sur la Cage (C = 19.33 pF)")
                c1, c2, c3, c4 = st.columns(4)
                
                c1.metric(
                    label="Rendement de Filtration Estimé",
                    value=f"{estimated_eff_faraday * 100.0:.3f} %"
                )
                
                c2.metric(
                    label="Courant d'Induction Cage (I_far)",
                    value=f"{st.session_state.ema_faraday_state:.2f} nA",
                    delta=f"{q_faraday_p
