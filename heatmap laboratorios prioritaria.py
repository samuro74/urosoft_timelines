import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path


# ============================================================
# CONFIGURACIÓN
# ============================================================

ARCHIVO = "ordenes_laboratorios.csv"

ARCHIVO_SALIDA = Path("heatmap_laboratorios_urgencias.html")

ENCODING = "cp1252"
SEPARADOR = "\t"


# ============================================================
# 1. CARGAR INFORMACIÓN
# ============================================================

print("Cargando archivo...")

df = pd.read_csv(
    ARCHIVO,
    sep=SEPARADOR,
    encoding=ENCODING,
    low_memory=False
)

print(f"Registros originales: {len(df):,}")


# ============================================================
# 2. CONVERTIR FECHA DE SOLICITUD
# ============================================================

df["fecha_solicitud_orden"] = pd.to_datetime(
    df["fecha_solicitud_orden"],
    errors="coerce"
)

# Eliminar registros sin fecha válida
df = df.dropna(subset=["fecha_solicitud_orden"])


# ============================================================
# 3. APLICAR LOS MISMOS FILTROS DE POWER QUERY
# ============================================================

df = df[
    (df["departamento"].astype(str).str.strip() == "URGENCIAS PRIORITARIA")
    &
    (df["ambulatorio"].astype(str).str.strip() == "HOSPITALARIA")
].copy()

print(f"Registros después de filtros: {len(df):,}")


# ============================================================
# 4. NORMALIZAR MÉDICO
# ============================================================

df["medico_solicitante"] = (
    df["medico_solicitante"]
    .fillna("SIN MÉDICO REGISTRADO")
    .astype(str)
    .str.strip()
)

df.loc[
    df["medico_solicitante"].isin(["", "nan", "None"]),
    "medico_solicitante"
] = "SIN MÉDICO REGISTRADO"


# ============================================================
# 5. CREAR VARIABLES TEMPORALES
# ============================================================

# Año
df["año"] = df["fecha_solicitud_orden"].dt.year

# Mes como período
df["mes"] = df["fecha_solicitud_orden"].dt.to_period("M")

# Texto para visualización
df["mes_texto"] = df["mes"].astype(str)

# Hora
df["hora"] = df["fecha_solicitud_orden"].dt.hour


# ============================================================
# 6. ORDENAR MÉDICOS Y MESES
# ============================================================

medicos = sorted(
    df["medico_solicitante"].unique()
)

meses = sorted(
    df["mes"].unique()
)

horas = list(range(24))


# ============================================================
# 7. CREAR FIGURA
# ============================================================

fig = go.Figure()


# ============================================================
# 8. CREAR UN HEATMAP POR CADA MÉDICO
# ============================================================

for i, medico in enumerate(medicos):

    datos_medico = df[
        df["medico_solicitante"] == medico
    ]

    matriz = (
        datos_medico
        .groupby(["mes", "hora"])
        .size()
        .unstack(fill_value=0)
        .reindex(
            index=meses,
            columns=horas,
            fill_value=0
        )
    )

    # Transponer para que las horas queden en Y
    matriz = matriz.T

    fig.add_trace(
        go.Heatmap(
            z=matriz.values,
            x=[str(x) for x in meses],
            y=[f"{h:02d}:00" for h in horas],
            colorscale="YlOrRd",
            colorbar=dict(
                title="Órdenes"
            ),
            hovertemplate=(
                "<b>Médico:</b> " + medico +
                "<br><b>Mes:</b> %{x}" +
                "<br><b>Hora:</b> %{y}" +
                "<br><b>Órdenes:</b> %{z:,}" +
                "<extra></extra>"
            ),
            visible=(i == 0)
        )
    )


# ============================================================
# 9. DROPDOWN DE MÉDICOS
# ============================================================

botones = []

for i, medico in enumerate(medicos):

    visibilidad = [False] * len(medicos)
    visibilidad[i] = True

    botones.append(
        dict(
            label=medico,
            method="update",
            args=[
                {"visible": visibilidad},
                {
                    "title": (
                        "Órdenes de laboratorio por hora y mes<br>"
                        f"<b>{medico}</b>"
                    )
                }
            ]
        )
    )


# ============================================================
# 10. CONFIGURACIÓN DEL GRÁFICO
# ============================================================

fig.update_layout(

    title=dict(
        text=(
            "Órdenes de laboratorio por hora y mes<br>"
            f"<b>{medicos[0]}</b>"
        ),
        x=0.5,
        xanchor="center"
    ),

    xaxis=dict(
        title="Mes",
        type="category",
        tickangle=-45
    ),

    yaxis=dict(
        title="Hora de solicitud",
        autorange="reversed"
    ),

    updatemenus=[
        dict(
            buttons=botones,
            direction="down",
            showactive=True,
            x=1.02,
            xanchor="left",
            y=1,
            yanchor="top"
        )
    ],

    height=800,

    margin=dict(
        l=100,
        r=300,
        t=120,
        b=120
    ),

    template="plotly_white"
)


# ============================================================
# 11. GUARDAR HTML
# ============================================================

fig.write_html(
    ARCHIVO_SALIDA,
    include_plotlyjs=True,
    full_html=True
)


# ============================================================
# 12. INFORMACIÓN FINAL
# ============================================================

print()
print("=" * 70)
print("ANÁLISIS FINALIZADO")
print("=" * 70)

print(f"Registros analizados: {len(df):,}")
print(f"Médicos encontrados: {len(medicos):,}")
print(f"Meses analizados: {len(meses):,}")

print()
print("Médicos:")

for medico in medicos:
    cantidad = (
        df["medico_solicitante"] == medico
    ).sum()

    print(f"  - {medico}: {cantidad:,} órdenes")

print()
print(f"Archivo generado:")
print(ARCHIVO_SALIDA)
print("=" * 70)
