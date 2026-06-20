import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque

class GasStream:
    """Simule le flux de gaz chargé en particules à l'entrée du filtre."""
    def __init__(self, base_concentration=1000.0, noise_std=50.0):
        self.base_concentration = base_concentration # mg/m^3
        self.noise_std = noise_std

    def get_input_concentration(self):
        """Retourne la concentration d'entrée avec une fluctuation stochastique."""
        return max(0, np.random.normal(self.base_concentration, self.noise_std))

class BaghouseFilter:
    """Modélise le filtre à manches et son rendement."""
    def __init__(self, initial_efficiency=0.999):
        self.efficiency = initial_efficiency # Rendement nominal (ex: 99.9%)
        self.is_damaged = False

    def trigger_damage(self, new_efficiency=0.985):
        """Simule une rupture de manche entraînant une chute de rendement."""
        self.efficiency = new_efficiency
        self.is_damaged = True

    def filter_gas(self, input_concentration):
        """Calcule la concentration de poussière s'échappant du filtre."""
        return input_concentration * (1.0 - self.efficiency)

class TriboelectricSensor:
    """Modélise le capteur électrostatique mesurant la charge des particules."""
    def __init__(self, calibration_factor=2.5, noise_std=0.5):
        # Le facteur de calibration convertit la concentration (mg/m^3) en signal (pA - picoAmpères)
        self.k = calibration_factor 
        self.noise_std = noise_std

    def read_signal(self, output_concentration):
        """Génère le signal électrique proportionnel à la charge détectée + bruit de ligne."""
        signal_ideal = self.k * output_concentration
        noise = np.random.normal(0, self.noise_std)
        return max(0, signal_ideal + noise)

class SmartMonitor:
    """Traite le signal, estime le rendement et détecte les anomalies."""
    def __init__(self, sensor_k, nominal_input_conc, alpha=0.1, alarm_threshold=0.99):
        self.sensor_k = sensor_k
        self.nominal_input_conc = nominal_input_conc
        self.alpha = alpha # Facteur de lissage pour la Moyenne Mobile Exponentielle (EMA)
        self.alarm_threshold = alarm_threshold
        self.filtered_signal = 0.0

    def process_data(self, raw_signal):
        """Filtre le signal et déduit les métriques de performance."""
        # Filtrage EMA (Exponential Moving Average) pour réduire le bruit
        if self.filtered_signal == 0.0:
            self.filtered_signal = raw_signal
        else:
            self.filtered_signal = (self.alpha * raw_signal) + ((1 - self.alpha) * self.filtered_signal)

        # Déduction de la concentration de sortie basée sur la calibration
        estimated_out_conc = self.filtered_signal / self.sensor_k

        # Calcul du rendement estimé
        estimated_efficiency = 1.0 - (estimated_out_conc / self.nominal_input_conc)
        
        # Logique d'alarme
        alarm = estimated_efficiency < self.alarm_threshold
        
        return estimated_out_conc, estimated_efficiency, alarm

# ==========================================
# CONFIGURATION DE LA SIMULATION TEMPS RÉEL
# ==========================================

# Initialisation des composants
stream = GasStream(base_concentration=1000.0)
bag_filter = BaghouseFilter(initial_efficiency=0.999) # 99.9% d'efficacité
sensor = TriboelectricSensor(calibration_factor=5.0, noise_std=1.2)
monitor = SmartMonitor(sensor_k=5.0, nominal_input_conc=1000.0, alpha=0.15, alarm_threshold=0.992)

# Paramètres de la fenêtre temporelle
window_size = 200
times = deque([0], maxlen=window_size)
raw_signals = deque([0], maxlen=window_size)
efficiencies = deque([1.0], maxlen=window_size)
alarms = deque([False], maxlen=window_size)

# Préparation de l'interface graphique
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
fig.canvas.manager.set_window_title('Monitoring Intelligent - Filtre à Manches')

line_raw, = ax1.plot([], [], lw=1.5, color='gray', label='Signal brut (pA)', alpha=0.5)
line_filtered, = ax1.plot([], [], lw=2, color='blue', label='Signal filtré (EMA)')
ax1.set_xlim(0, window_size)
ax1.set_ylim(0, 50)
ax1.set_ylabel('Charge Électrostatique (pA)')
ax1.set_title('Détection de la charge des particules en sortie')
ax1.legend(loc='upper right')
ax1.grid(True)

line_eff, = ax2.plot([], [], lw=2, color='green', label='Rendement estimé (%)')
threshold_line = ax2.axhline(y=99.2, color='red', linestyle='--', label='Seuil Alarme (99.2%)')
alarm_text = ax2.text(0.02, 0.1, '', transform=ax2.transAxes, color='red', fontsize=12, fontweight='bold')
ax2.set_xlim(0, window_size)
ax2.set_ylim(97.5, 100.1)
ax2.set_ylabel('Rendement (%)')
ax2.set_xlabel('Temps (Itérations)')
ax2.legend(loc='lower right')
ax2.grid(True)

time_step = [0]
filtered_history = deque([0], maxlen=window_size)

def update(frame):
    t = time_step[0]
    
    # 1. Injection d'une anomalie physique à t=100 (Déchirure d'une manche)
    if t == 100:
        bag_filter.trigger_damage(new_efficiency=0.985)
        
    # 2. Simulation de la physique
    c_in = stream.get_input_concentration()
    c_out = bag_filter.filter_gas(c_in)
    
    # 3. Mesure par le capteur (avec bruit électromagnétique)
    raw_sig = sensor.read_signal(c_out)
    
    # 4. Traitement par le Smart Monitor
    est_c_out, est_eff, is_alarm = monitor.process_data(raw_sig)
    
    # Mise à jour des historiques pour le graphique
    times.append(t)
    raw_signals.append(raw_sig)
    filtered_history.append(monitor.filtered_signal)
    efficiencies.append(est_eff * 100) # Conversion en pourcentage
    alarms.append(is_alarm)
    
    # Ajustement de l'axe X pour l'effet de défilement (scrolling)
    if t >= window_size:
        ax1.set_xlim(t - window_size, t)
        ax2.set_xlim(t - window_size, t)
        
    # Mise à jour des courbes
    line_raw.set_data(times, raw_signals)
    line_filtered.set_data(times, filtered_history)
    
    # Coloration dynamique de la courbe de rendement
    line_eff.set_data(times, efficiencies)
    if is_alarm:
        line_eff.set_color('red')
        alarm_text.set_text('⚠️ ALARME : CHUTE DE RENDEMENT DÉTECTÉE !')
        fig.patch.set_facecolor('#ffe6e6') # Clignotement du fond en rouge
    else:
        line_eff.set_color('green')
        alarm_text.set_text('Système Normal')
        fig.patch.set_facecolor('white')
        
    time_step[0] += 1
    return line_raw, line_filtered, line_eff, alarm_text

# Lancement de la boucle d'animation
ani = animation.FuncAnimation(fig, update, frames=1000, interval=100, blit=False)

plt.tight_layout()
plt.show()
