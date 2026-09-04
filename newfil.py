import matplotlib.pyplot as plt
import numpy as np

# Set matplotlib style/fonts
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['axes.edgecolor'] = '#111111'
plt.rcParams['axes.linewidth'] = 0.8

fig, ax = plt.subplots(figsize=(10, 6), dpi=300)

# Grid
ax.grid(True, color='#e5e5e5', linestyle='-', linewidth=1, zorder=0)

# Data for Gaussian curve
d = np.linspace(0, 150, 500)
sigma_d = 80
y_gauss = 1.0 - np.exp(- (d**2) / (2.0 * sigma_d**2))

# Data for Echelon curve
d_th = 50
y_echelon_low = np.zeros_like(d[d < d_th])
d_low = d[d < d_th]

y_echelon_high = np.ones_like(d[d >= d_th])
d_high = d[d >= d_th]

# Colors
red_color = '#c0392b'
blue_color = '#1f5fa0'

# Plot Echelon lines
ax.plot(d_low, y_echelon_low, color=red_color, linewidth=3.5, label=r'Échelon (seuil $d_{th} = 50$ m)', zorder=3)
ax.plot(d_high, y_echelon_high, color=red_color, linewidth=3.5, zorder=3)

# Dotted vertical line at d = 50
ax.plot([50, 50], [0, 1], color=red_color, linestyle=':', linewidth=2.5, zorder=2)

# Open circle at (50, 0) and filled circle at (50, 1)
ax.plot(50, 0, marker='o', markersize=8, markerfacecolor='white', markeredgecolor=red_color, markeredgewidth=2, zorder=4)
ax.plot(50, 1, marker='o', markersize=8, markerfacecolor=red_color, markeredgecolor=red_color, zorder=4)

# Plot Gaussian curve
ax.plot(d, y_gauss, color=blue_color, linewidth=3.5, label=r'Gaussien ($\sigma_d = 80$ m)', zorder=3)

# Annotation for red curve ("saut brutal")
ax.annotate(
    "saut brutal\n$0 \\rightarrow 1$",
    xy=(50, 0.5),
    xytext=(70, 0.45),
    color=red_color,
    fontsize=13,
    ha='left',
    va='center',
    arrowprops=dict(arrowstyle='->', color=red_color, lw=1.5)
)

# Annotation for blue curve ("transition douce") - MODIFIED POSITION (ABOVE THE CURVE)
ax.annotate(
    "transition douce",
    xy=(95, 0.52),
    xytext=(94, 0.66),
    color=blue_color,
    fontsize=10,
    ha='left',
    va='center',
    arrowprops=dict(arrowstyle='->', color=blue_color, lw=1.5)
)

# Axes limits and labels
ax.set_xlim(0, 150)
ax.set_ylim(-0.05, 1.1)

ax.set_title("Non-redondance spatiale : seuil (échelon) vs noyau gaussien", fontsize=16, pad=12)
ax.set_xlabel("Distance au voisin caché  $d$  (m)", fontsize=13, labelpad=8)
ax.set_ylabel("Facteur spatial  ($1 - S$)", fontsize=13, labelpad=8)

# Legend
ax.legend(loc='lower right', fontsize=12, frameon=True, facecolor='white', edgecolor='#cccccc', framealpha=1.0)

# Save as PDF and PNG
plt.tight_layout()
plt.savefig('figure_non_redondance_modifiee.pdf', format='pdf', dpi=300)
plt.savefig('figure_non_redondance_modifiee.png', format='png', dpi=300)
print("Saved figure_non_redondance_modifiee.pdf and png successfully!")