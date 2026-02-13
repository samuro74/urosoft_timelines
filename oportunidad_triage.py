import pandas as pd
import numpy as np

# =========================================
# CONFIGURACIÓN
# =========================================

RUTA_INGRESOS = "Ingresos_Consultorios.csv"
RUTA_EVOLUCIONES = "medicos_evoluciones.csv"

MEDICO_VISIBLE = None  
# Escriba el nombre exacto si desea dejar uno visible.
# Ejemplo:
# MEDICO_VISIBLE = ""

# =========================================
# CARGA
# =========================================

ingresos = pd.read_csv(
    RUTA_INGRESOS,
    sep="\t",
    encoding="latin1",
    parse_dates=["fechaingreso", "fecha_consulta"]
)

evoluciones = pd.read_csv(
    RUTA_EVOLUCIONES,
    sep="\t",
    encoding="latin1",
    parse_dates=["fecha_evolucion"]
)

# =========================================
# FILTRO SERVICIO
# =========================================

ingresos = ingresos[
    ingresos["departamento_ingreso"] == "URGENCIAS CONSULTORIOS Y PROCEDIMIENTOS"
].copy()

# Asegurar ingreso como texto
ingresos["ingreso"] = ingresos["ingreso"].astype(str)
evoluciones["ingreso"] = evoluciones["ingreso"].astype(str)

# =========================================
# TIEMPO DE ESPERA
# =========================================

ingresos["duracion"] = ingresos["fecha_consulta"] - ingresos["fechaingreso"]
ingresos["minutos_espera"] = ingresos["duracion"].dt.total_seconds() / 60

# =========================================
# FUNCIÓN BUSCAR EVOLUCIONES EN ESPERA
# =========================================

def buscar_evoluciones(row):
    
    if row["minutos_espera"] <= 20:
        return "No aplica (≤20 min)"
    
    inicio = row["fechaingreso"]
    fin = row["fecha_consulta"]
    medico = row["medico"]
    
    evos = evoluciones[
        (evoluciones["medico"] == medico) &
        (evoluciones["fecha_evolucion"] >= inicio) &
        (evoluciones["fecha_evolucion"] <= fin)
    ]
    
    if evos.empty:
        return "Sin evoluciones en ese intervalo"
    
    fechas = evos["fecha_evolucion"].dt.strftime("%Y-%b-%d %H:%M:%S").tolist()
    return " | ".join(fechas)

# Aplicar
ingresos["evoluciones_en_espera"] = ingresos.apply(buscar_evoluciones, axis=1)

# =========================================
# FORMATO DE FECHAS
# =========================================

ingresos["fechaingreso"] = ingresos["fechaingreso"].dt.strftime("%Y-%b-%d %H:%M:%S")
ingresos["fecha_consulta"] = ingresos["fecha_consulta"].dt.strftime("%Y-%b-%d %H:%M:%S")

# =========================================
# ANONIMIZACIÓN OPCIONAL
# =========================================

if MEDICO_VISIBLE:

    medicos = (
        ingresos.loc[ingresos["medico"] != MEDICO_VISIBLE, "medico"]
        .dropna()
        .unique()
    )

    mapa_anon = {medico: f"medico{i+1}" for i, medico in enumerate(medicos)}

    ingresos["medico"] = ingresos["medico"].apply(
        lambda x: x if x == MEDICO_VISIBLE else mapa_anon.get(x, x)
    )

# =========================================
# TABLA FINAL
# =========================================

columnas_finales = [
    "ingreso",
    "plan_descripcion",
    "medico",
    "fechaingreso",
    "fecha_consulta",
    "minutos_espera",
    "evoluciones_en_espera"
]

tabla_final = ingresos[columnas_finales].copy()

display(tabla_final)

# =========================================
# PROMEDIOS
# =========================================

promedio_general = tabla_final["minutos_espera"].mean()

promedio_por_medico = (
    tabla_final
    .groupby("medico")["minutos_espera"]
    .mean()
    .reset_index()
    .sort_values("minutos_espera", ascending=False)
)

print("\nPROMEDIO GENERAL DE MINUTOS DE ESPERA:")
print(round(promedio_general, 2))

print("\nPROMEDIO DE MINUTOS DE ESPERA POR MÉDICO:")
display(promedio_por_medico)
