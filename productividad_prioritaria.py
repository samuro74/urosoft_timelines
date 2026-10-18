"""
Reporte de productividad de médicos del departamento_ingreso = 'URGENCIAS PRIORITARIA'

Reglas de negocio:
- Horas urgenciando     = pacientes atendidos / 3
- Horas con especialista = pacientes atendidos / 2
- Horas totales         = horas urgenciando + horas con especialista
- Redondeo positivo (hacia arriba, ceil) sobre los valores finales

Entrada : Ingresos_Consultorios.csv (separado por TAB, encoding 1252)
Salida  : reporte_productividad_prioritaria.csv
"""

import math
import pandas as pd

# ------------------------------------------------------------------
# 1. Configuración
# ------------------------------------------------------------------
ARCHIVO_ENTRADA = "Ingresos_Consultorios.csv"
ARCHIVO_SALIDA  = "reporte_productividad_prioritaria.csv"
DEPARTAMENTO    = "URGENCIAS PRIORITARIA"

# ------------------------------------------------------------------
# 2. Lectura del CSV (equivalente a tu consulta M)
#    - Delimitador TAB
#    - Encoding 1252 (Windows-1252)
#    - Sin comillas
# ------------------------------------------------------------------
df = pd.read_csv(
    ARCHIVO_ENTRADA,
    sep="\t",
    encoding="cp1252",
    quoting=3,            # QUOTE_NONE
    dtype=str,            # leemos todo como texto y convertimos lo necesario
    keep_default_na=False,
)

# Normalizar nombres de columnas (por si vienen con espacios/BOM)
df.columns = [c.strip().replace("\ufeff", "") for c in df.columns]

# ------------------------------------------------------------------
# 3. Conversión de tipos (equivalente a Table.TransformColumnTypes)
# ------------------------------------------------------------------
def a_int(s):
    return pd.to_numeric(s, errors="coerce").astype("Int64")

def a_datetime(s):
    return pd.to_datetime(s, errors="coerce")

df["fecha_consulta"]       = a_datetime(df.get("fecha_consulta"))
df["fechaingreso"]         = a_datetime(df.get("fechaingreso"))
df["fechacierre_ingreso"]  = a_datetime(df.get("fechacierre_ingreso"))
df["numerodecuenta"]       = a_int(df.get("numerodecuenta"))
df["total_cuenta"]         = a_int(df.get("total_cuenta"))

# Limpieza de textos clave
for col in ["departamento_ingreso", "medico"]:
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip()

# ------------------------------------------------------------------
# 4. Filtro: solo URGENCIAS PRIORITARIA
# ------------------------------------------------------------------
df_f = df[df["departamento_ingreso"].str.upper() == DEPARTAMENTO.upper()].copy()

# Descartar registros sin médico o sin fecha de consulta
df_f = df_f.dropna(subset=["medico", "fecha_consulta"])
df_f = df_f[df_f["medico"].str.strip() != ""]

# ------------------------------------------------------------------
# 5. Agrupación médico / día
# ------------------------------------------------------------------
df_f["dia"] = df_f["fecha_consulta"].dt.date

# Contamos pacientes atendidos = cuentas únicas por médico y día
# (evita duplicar si un mismo ingreso/numerodecuenta aparece varias veces)
resumen = (
    df_f.groupby(["medico", "dia"], dropna=False)
        .agg(
            pacientes_atendidos=("numerodecuenta", "nunique"),
            registros=("numerodecuenta", "size"),
        )
        .reset_index()
)

# Si no hubiera numerodecuenta, usamos registros como respaldo
resumen["pacientes_atendidos"] = resumen["pacientes_atendidos"].where(
    resumen["pacientes_atendidos"] > 0, resumen["registros"]
)

# ------------------------------------------------------------------
# 6. Cálculos de horas con REDONDEO POSITIVO (ceil)
#    horas_urgenciando      = pacientes / 3
#    horas_con_especialista = pacientes / 2
#    horas_totales          = suma de las dos anteriores (ya redondeadas)
# ------------------------------------------------------------------
resumen["horas_urgenciando"]      = resumen["pacientes_atendidos"].apply(
    lambda n: math.ceil(n / 3) if pd.notna(n) else 0
)
resumen["horas_con_especialista"] = resumen["pacientes_atendidos"].apply(
    lambda n: math.ceil(n / 2) if pd.notna(n) else 0
)
resumen["horas_totales"]          = (
    resumen["horas_urgenciando"] + resumen["horas_con_especialista"]
)

# ------------------------------------------------------------------
# 7. Formato final del reporte
# ------------------------------------------------------------------
reporte = resumen[[
    "medico",
    "dia",
    "pacientes_atendidos",
    "horas_urgenciando",
    "horas_con_especialista",
    "horas_totales",
]].rename(columns={
    "medico":                 "Medico",
    "dia":                    "Dia",
    "pacientes_atendidos":    "Pacientes_Atendidos",
    "horas_urgenciando":      "Horas_Urgenciando",
    "horas_con_especialista": "Horas_Con_Especialista",
    "horas_totales":          "Horas_Totales",
})

# Orden: médico y día
reporte = reporte.sort_values(["Medico", "Dia"]).reset_index(drop=True)

# ------------------------------------------------------------------
# 8. Exportación CSV
# ------------------------------------------------------------------
reporte.to_csv(ARCHIVO_SALIDA, index=False, encoding="utf-8-sig")

print(f"Reporte generado: {ARCHIVO_SALIDA}")
print(f"Registros: {len(reporte)}")
print(reporte.head(20).to_string(index=False))
