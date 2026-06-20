import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import pandas as pd
import io

# Configuration de la page
st.set_page_config(
    page_title="SmartFilter Monitor",
    layout="wide"
)

# En-tête principal épuré
st.title("SmartFilter Monitor")
st.subheader("Supervision Haute Température & Diagnostic Électrostatique - Application Cimenterie")

# --- COEUR DE MODÉLISATION PHYSIQUE DES DEUX TECHNOLOGIES ---
class CementFilterAdvancedSimulation:
    def __init__(self):
        # Paramètres procédé généraux
        self.base_concentration = 1200.0  # mg/m^3 (Charge brute du four)
        self.nominal_efficiency = 0.9995  # 99.95% (Opération nominale)
        self.t_critique_tissu = 240.0     # Limite du Polyimide P84 (°C)
        self.debit_air_nominal = 100000.0 # m^3/h

        # Paramètres spécifiques : Capteur 1 (Sonde à Impact classique)
        self.k_impact_zero = 4.0          # Gain initial par impact
        self.noise_impact = 6.5           # Bruit fort (Pas de blindage Faraday)
        
        # Paramètres spécifiques : Capteur 2 (Votre Cage de Faraday coaxiale)
        self.k_faraday_zero = 5.0         # Gain initial par induction
        self.noise_faraday = 1.2          # Bruit très faible (Blindage par cylindre externe)

        self.alpha = 0.15                 # Coefficient du filtre EMA

    def generate_data_point(self, t, is_mechanically_damaged, temperature, fouling_active):
        # 1. Simulation de la dégradation des manches (Thermique ou Mécanique)
        thermal_damage = temperature > self.t_critique_tissu
        if is_mechanically_damaged or thermal_damage:
            current_eff = 0.978  
        else:
            current_eff = self.nominal_efficiency
         
        # 2. Concentration réelle en sortie du filtre
        c_in = max(0.0, np.random.normal(self.base_concentration, 60.0))
        c_out = c_in * (1.0 - current_eff)
         
        # 3. Effet de la température sur la dynamique gazeuse (dilatation)
        facteur_temperature = np.sqrt((temperature + 273.15) / 293.15)
        
        # --- CAPTEUR 1 : MESURE PAR IMPACT ---
        if fouling_active:
            facteur_encrassement = np.exp(-0.015 * t)  # Perte de sensibilité continue
        else:
            facteur_encrassement = 1.0
            
        gain_impact = self.k_impact_zero * facteur_temperature * facteur_encrassement
        raw_impact = max(0.0, (c_out * gain_impact) + np.random.normal(0.0, self.noise_impact))

        # --- CAPTEUR 2 : CAGE DE FARADAY (ÉCOULEMENT) ---
        gain_faraday = self.k_faraday_zero * facteur_temperature
        raw_faraday = max(0.0, (c_out * gain_faraday) + np.random.normal(0.0, self.noise_faraday))
         
        return raw_impact, raw_faraday, current_eff, thermal_damage, facteur_encrassement

# Initialisation
sim = CementFilterAdvancedSimulation()

# --- ONGLETS ---
tab1, tab2 = st.tabs(["📊 Supervision Process Temps Réel", "🔬 Fiche Technique Tissu & Équations"])

# ==========================================
# ONGLET 1 : SUPERVISION EN TEMPS RÉEL
# ==========================================
with tab1:
    st.sidebar.header("Paramètres Opérationnels")
    run_simulation = st.sidebar.toggle("Démarrer le monitoring", value=True)
     
    st.sidebar.markdown("---")
    st.sidebar.subheader("Contrôle du Procédé Four/Broyeur")
    gas_temp = st.sidebar.slider("Température des gaz entrants (°C)", 120, 280, 210)
    trigger_mechanical = st.sidebar.toggle("Simuler une déchirure mécanique", value=False)
    trigger_fouling = st.sidebar.toggle("Activer l'encrassement (Sonde Impact)", value=True)
    speed = st.sidebar.slider("Fréquence d'échantillonnage (s)", 0.1, 1.0, 0.3)

    # --- INITIALISATION INDÉPENDANTE DE CHAQUE VARIABLE ---
    if 'time_steps' not in st.session_state:
        st.session_state.time_steps = []
    if 'raw_impact' not in st.session_state:
        st.session_state.raw_impact = []
    if 'filtered_impact' not in st.session_state:
        st.session_state.filtered_impact = []
    if 'raw_faraday' not in st.session_state:
        st.session_state.raw_faraday = []
    if 'filtered_faraday' not in st.session_state:
        st.session_state.filtered_faraday = []
    if 'efficiencies_faraday' not in st.session_state:
        st.session_state.efficiencies_faraday = []
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 0
    if 'ema_impact_state' not in st.session_state:
        st.session_state.ema_impact_state = None
    if 'ema_faraday_state' not in st.session_state:
        st.session_state.ema_faraday_state = None

    st.sidebar.markdown("---")
    st.sidebar.subheader("🛠️ Actions & Export")

    if st.sidebar.button("Réinitialiser l'historique"):
        st.session_state.time_steps = []
        st.session_state.raw_impact = []
        st.session_state.filtered_impact = []
        st.session_state.raw_faraday = []
        st.session_state.filtered_faraday = []
        st.session_state.efficiencies_faraday = []
        st.session_state.current_step = 0
        st.session_state.ema_impact_state = None
        st.session_state.ema_faraday_state = None
        st.rerun()

    # --- CORRECTION ET SÉCURISATION DU BLOC D'EXPORTATION EXCEL ---
    lengths = [
        len(st.session_state.time_steps),
        len(st.session_state.raw_impact),
        len(st.session_state.filtered_impact),
        len(st.session_state.raw_faraday),
        len(st.session_state.filtered_faraday),
        len(st.session_state.efficiencies_faraday)
    ]
    min_len = min(lengths) if lengths else 0

    if min_len > 0:
        # Création sécurisée avec indexation synchronisée à min_len
        df_export = pd.DataFrame({
            "Temps (Iterations)": list(st.session_state.time_steps)[:min_len],
            "Sonde Impact - Brute (pC)": list(st.session_state.raw_impact)[:min_len],
            "Sonde Impact - Filtree EMA (pC)": list(st.session_state.filtered_impact)[:min_len],
            "Cage Faraday - Brute (pC)": list(st.session_state.raw_faraday)[:min_len],
            "Cage Faraday - Filtree EMA (pC)": list(st.session_state.filtered_faraday)[:min_len],
            "Rendement Estime par Cage Faraday (%)": list(st.session_state.efficiencies_faraday)[:min_len]
        })
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name="Comparatif_Capteurs")
        excel_buffer.seek(0)
        
        st.sidebar.download_button(
            label="📥 Télécharger l'étude comparative (.xlsx)",
            data=excel_buffer,
            file_name="comparatif_impact_vs_faraday.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="excel_download"
        )
    else:
        st.sidebar.caption("⏳ En attente de signaux pour l'exportation...")

    placeholder = st.empty()

    if run_simulation:
        while True:
            t = st.session_state.current_step
            r_impact, r_faraday, true_eff, t_damage, f_impact_ratio = sim.generate_data_point(
                t, trigger_mechanical, gas_temp, trigger_fouling
            )
             
            # Traitement par filtre numérique (EMA) pour la sonde à Impact
            if st.session_state.ema_impact_state is None:
                st.session_state.ema_impact_state = r_impact
            else:
                st.session_state.ema_impact_state = (sim.alpha * r_impact) + ((1.0 - sim.alpha) * st.session_state.ema_impact_state)
             
            # Traitement par filtre numérique (EMA) pour la Cage de Faraday
            if st.session_state.ema_faraday_state is None:
                st.session_state.ema_faraday_state = r_faraday
            else:
                st.session_state.ema_faraday_state = (sim.alpha * r_faraday) + ((1.0 - sim.alpha) * st.session_state.ema_faraday_state)
             
            # Inversion mathématique thermodynamique pour estimer le rendement via votre Cage de Faraday
            facteur_t = np.sqrt((gas_temp + 273.15) / 293.15)
            dynamic_gain_faraday = sim.k_faraday_zero * facteur_t
            estimated_c_out_faraday = st.session_state.ema_faraday_state / dynamic_gain_faraday
            estimated_eff_faraday = 1.0 - (estimated_c_out_faraday / sim.base_concentration)
            
            # Débit massique absolu (kg/h)
            flux_massique_kgh = (estimated_c_out_faraday * sim.debit_air_nominal) / 1000000.0
             
            # Remplissage des buffers historiques (limités aux 100 dernières itérations)
            st.session_state.time_steps.append(t)
            st.session_state.raw_impact.append(r_impact)
            st.session_state.filtered_impact.append(st.session_state.ema_impact_state)
            st.session_state.raw_faraday.append(r_faraday)
            st.session_state.filtered_faraday.append(st.session_state.ema_faraday_state)
            st.session_state.efficiencies_faraday.append(estimated_eff_faraday * 100.0)
             
            if len(st.session_state.time_steps) > 100:
                st.session_state.time_steps.pop(0)
                st.session_state.raw_impact.pop(0)
                st.session_state.filtered_impact.pop(0)
                st.session_state.raw_faraday.pop(0)
                st.session_state.filtered_faraday.pop(0)
                st.session_state.efficiencies_faraday.pop(0)
                 
            # --- CONFIGURATION DU TRACÉ DES GRAPHES COMPARATIFS ---
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                                subplot_titles=("Sonde Triboélectrique par Impact Classique (Non blindée)", 
                                                "Votre Capteur Coaxial à Écoulement (Cage de Faraday Blindée)", 
                                                "Rendement Calculé par la Cage de Faraday (%)"))
            
            # Graphe 1 : Sonde classique à Impact
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.raw_impact),
                                     name="Impact : Brute", line=dict(color='rgba(219, 68, 85, 0.3)', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_impact),
                                     name="Impact : Filtrée (EMA)", line=dict(color='#db4455', width=2)), row=1, col=1)
            
            # Graphe 2 : Votre Cage de Faraday
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.raw_faraday),
                                     name="Faraday : Brute", line=dict(color='rgba(31, 119, 180, 0.3)', width=1)), row=2, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_faraday),
                                     name="Faraday : Filtrée (EMA)", line=dict(color='#1f77b4', width=2.5)), row=2, col=1)
            
            # Graphe 3 : Rendement déduit par la technique stable (Faraday)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.efficiencies_faraday),
                                     name="Rendement Faraday", line=dict(color='#2ca02c', width=2.5)), row=3, col=1)
            fig.add_hline(y=99.2, line_dash="dash", line_color="orange", annotation_text="Seuil Alarme (99.2%)", row=3, col=1)
             
            fig.update_layout(height=700, showlegend=True, margin=dict(l=20, r=20, t=30, b=10))
            fig.update_yaxes(title_text="Signal (pC)", row=1, col=1)
            fig.update_yaxes(title_text="Signal (pC)", row=2, col=1)
            fig.update_yaxes(title_text="Rendement (%)", row=3, col=1)
            fig.update_xaxes(title_text="Temps (Itérations)", row=3, col=1)
             
            with placeholder.container():
                # Alarmes de sécurité
                if t_damage:
                    st.error(f"🚨 STRATIFICATION THERMIQUE CRITIQUE : Gaz à {gas_temp}°C > Seuil P84 (240°C). Rupture physique imminente.")
                elif estimated_eff_faraday < 0.992:
                    st.warning(f"⚠️ SIGNAL DE FUITE RECONNU : La cage de Faraday confirme une baisse de filtration.")
                else:
                    st.success(f"✅ STATUT FILTRE NOMINAL : Écoulement stable à {gas_temp}°C à travers la maille.")
                
                # SECTION AFFICHEURS COMPARES
                st.markdown("### 🎛️ Métriques Comparatives des Deux Technologies")
                c1, c2, c3 = st.columns(3)
                
                c1.metric(
                    label="Rendement Réel (Calculé via Faraday)",
                    value=f"{estimated_eff_faraday * 100.0:.3f} %",
                    delta=f"-{(0.9995 - estimated_eff_faraday)*100:.3f} %" if estimated_eff_faraday < 0.9995 else None,
                    delta_color="inverse"
                )
                
                c2.metric(
                    label="Signal Cage de Faraday (Stable)",
                    value=f"{st.session_state.ema_faraday_state:.2f} pC",
                    delta="Immunisé encrassement"
                )
                
                c3.metric(
                    label="Signal Sonde Impact (Perte d'efficacité)",
                    value=f"{st.session_state.ema_impact_state:.2f} pC",
                    delta=f"Efficacité Capteur: {f_impact_ratio*100:.1f}%",
                    delta_color="normal" if f_impact_ratio > 0.8 else "inverse"
                )
                
                st.markdown("---")
                st.plotly_chart(fig, use_container_width=True)
                 
            st.session_state.current_step += 1
            time.sleep(speed)
    else:
        st.info("Simulation en pause. Utilisez le volet latéral pour démarrer le monitoring comparatif.")

# ==========================================
# ONGLET 2 : FICHE TECHNIQUE TISSU & ÉQUATIONS
# ==========================================
with tab2:
    st.header("Étude Comparative de la Captation Électrostatique")
    
    st.markdown("### 📊 Analyse Comparative : Impact Triboélectrique vs Induction Coaxiale")
    
    # Tableau comparatif direct des technologies
    st.markdown("#### Tableau Synoptique Industriel")
    compa_data = {
        "Critère d'évaluation": [
            "Physique fondamentale",
            "Sensibilité à l'encrassement",
            "Niveau de bruit de fond (EMI)",
            "Niveau de maintenance requis",
            "Évolution temporelle du gain"
        ],
        "Sonde à Impact Classique": [
            "Choc mécanique direct et transfert de charge par friction locale.",
            "Très élevée. La poussière de ciment crée une couche isolante sur la tige.",
            "Élevé. L'absence de blindage capte les parasites des moteurs et variateurs.",
            "Fréquente (Nécessite des nettoyages pneumatiques réguliers).",
            "Décroissant. Le signal s'atténue à mesure que la sonde s'encrasse."
        ],
        "Votre Cage de Faraday (Écoulement)": [
            "Théorème de Gauss. Induction électrostatique sans contact à travers un flux continu.",
            "Nul. Aucun contact requis avec l'élément de mesure central.",
            "Extrêmement faible. Le cylindre externe fait office de blindage à la masse.",
            "Quasi inexistante (Géométrie coaxiale autonettoyante par le flux gazeux).",
            "Constant et stable. Uniquement lié à la température et au débit."
        ]
    }
    st.table(compa_data)

    st.markdown("---")
    st.subheader("🔬 Équations de Modélisation du Capteur Coaxial (Faraday)")
     
    st.markdown("#### A. Application du Théorème de Gauss")
    st.write("Lorsqu'un nuage de particules portant une charge volumique intrinsèque $q_v(t)$ s'écoule au centre du cylindre de mesure interne, une charge électrique strictement opposée est induite à sa surface par influence totale :")
    st.latex(r"Q_{induit}(t) = - \iiint_{v} q_v(t) \cdot dV")
    st.write("Le cylindre coaxial externe est maintenu au potentiel zéro de la terre ($V_{exterieur} = 0\\text{ V}$), annulant le champ électrique externe d'origine parasite.")

    st.markdown("#### B. Dynamique d'atténuation de la sonde d'impact")
    st.write("À l'inverse, la perte d'efficacité de captation par impact due à l'accumulation de poussières de ciment suit une loi de dégradation exponentielle, paramétrée dans l'application :")
    st.latex(r"k_{impact}(t) = k_{0, impact} \cdot \sqrt{\frac{T_{gaz} + 273.15}{293.15}} \cdot e^{-\lambda t}")
    st.write("Où $\\lambda$ représente le coefficient d'encrassement. Cela explique pourquoi, sur vos graphiques, la courbe rouge s'effondre alors que votre courbe bleue (Faraday) reste stable et continue de surveiller fidèlement le rendement réel.")
