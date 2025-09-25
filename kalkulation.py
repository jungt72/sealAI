import pandas as pd

# Eingabeparameter
order_quantities = [1, 10, 25, 50, 100, 250, 500, 1000]
hourly_cost = 100              # € pro Stunde Fertigung
admin_cost = 250               # € pro Auftrag für Verwaltung
material_cost_per_piece = 0.60 # € pro Stück
# Berechnung der Zusatzkosten so, dass bei 1000 Stück der Stückpreis 2,87 € beträgt:
# Für 1000 Stück berechnet sich der bisherige Gesamtpreis:
production_cost_1000 = ((60 + 1000) / 60) * hourly_cost
material_cost_1000 = 1000 * material_cost_per_piece
base_total_1000 = production_cost_1000 + admin_cost + material_cost_1000
target_total_1000 = 2.87 * 1000
extra_cost = target_total_1000 - base_total_1000

data = []
for n in order_quantities:
    production_time_minutes = 60 + n  
    production_cost = (production_time_minutes / 60) * hourly_cost
    material_cost = n * material_cost_per_piece
    total_cost = production_cost + admin_cost + material_cost + extra_cost
    price_per_piece = total_cost / n
    data.append([n, production_time_minutes, production_cost, admin_cost, material_cost, extra_cost, total_cost, price_per_piece])

df = pd.DataFrame(
    data, 
    columns=["Menge", "Produktionszeit (Min)", "Produktionskosten (€)", "Verwaltung (€)", "Materialkosten (€)", "Zusatzkosten (€)", "Gesamtkosten (€)", "Stückpreis (€)"]
)
print(df)
