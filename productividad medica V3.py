# horas_medicos.py
import csv
import re
import pandas as pd

EVOLUCIONES_PATH = "medicos_evoluciones.csv"
CONSULTAS_PATH   = "Ingresos_Consultorios.csv"

# Huecos mayores a este umbral se consideran "horas muertas" y no suman.
UMBRAL_MINUTOS = 60


# ---------------------------------------------------------------------------
# Lectura TSV replicando la lógica de Power Query
# ---------------------------------------------------------------------------
def _leer_tsv(path: str) -> pd.DataFrame:
    return pd.read_csv(
        path,
        sep="\t",
        encoding="cp1252",
        dtype=str,
        quoting=csv.QUOTE_NONE,
        keep_default_na=False,
    )


def cargar_eventos() -> pd.DataFrame:
    """Une evoluciones + consultas en una sola tabla de eventos."""
    # --- Evoluciones ---
    ev = _leer_tsv(EVOLUCIONES_PATH)
    ev["timestamp"] = pd.to_datetime(ev["fecha_evolucion"], errors="coerce")
    ev["departamento"] = (
        ev["departamento"].fillna("").replace("", "SIN DEPARTAMENTO")
    )
    ev = ev[["medico", "departamento", "timestamp"]].copy()
    ev["fuente"] = "evolucion"

    # --- Consultas ---
    co = _leer_tsv(CONSULTAS_PATH)
    fc = pd.to_datetime(co["fecha_consulta"], errors="coerce")
    hc = pd.to_timedelta(
        co["hora_consulta"].replace("", pd.NA), errors="coerce"
    )
    # Si hora_consulta viene informada, se combina con la fecha; si no, se usa la fecha sola.
    co["timestamp"] = fc.where(hc.isna(), fc.dt.normalize() + hc)

    dep_act = co["departamento_actual"].fillna("")
    dep_ing = co["departamento_ingreso"].fillna("")
    co["departamento"] = (
        dep_act.where(dep_act != "", dep_ing)
              .replace("", "SIN DEPARTAMENTO")
    )
    co = co[["medico", "departamento", "timestamp"]].copy()
    co["fuente"] = "consulta"

    # --- Limpieza ---
    for df in (ev, co):
        df.dropna(subset=["timestamp", "medico"], inplace=True)
    ev = ev[ev["medico"].str.strip() != ""]
    co = co[co["medico"].str.strip() != ""]

    # --- Unión ---
    eventos = pd.concat([ev, co], ignore_index=True)
    eventos["timestamp"] = pd.to_datetime(eventos["timestamp"])
    eventos = eventos.sort_values("timestamp").reset_index(drop=True)
    eventos["fecha"] = eventos["timestamp"].dt.date
    return eventos


# ---------------------------------------------------------------------------
# Selección múltiple por consola
# ---------------------------------------------------------------------------
def _parsear_seleccion(texto: str, n: int) -> list[int] | None:
    """
    Acepta: '*' o Enter -> todos; '1,3,5' -> sueltos; '2-5' -> rango; combinaciones.
    Devuelve lista de índices 1-based o None (todos).
    """
    texto = texto.strip()
    if texto in ("", "*"):
        return None
    indices: set[int] = set()
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", parte)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                a, b = b, a
            indices.update(i for i in range(a, b + 1) if 1 <= i <= n)
        elif parte.isdigit():
            i = int(parte)
            if 1 <= i <= n:
                indices.add(i)
    return sorted(indices) if indices else None


def elegir_multi(prompt: str, opciones: list[str]) -> list[str] | None:
    print(f"\n{prompt}:")
    for i, o in enumerate(opciones, 1):
        print(f"  {i}. {o}")
    print("  (Enter o * = todos; ej: 1,3  ó  2-5  ó  1,3-5)")
    idx = _parsear_seleccion(input("Seleccione: "), len(opciones))
    return None if idx is None else [opciones[i - 1] for i in idx]


# ---------------------------------------------------------------------------
# Cálculo de horas activas descontando huecos
# ---------------------------------------------------------------------------
def _horas_activas(ts_series: pd.Series, umbral_min: int) -> tuple[float, float]:
    """Retorna (horas_activas, horas_span)."""
    ts = ts_series.sort_values().reset_index(drop=True)
    if len(ts) < 2:
        return 0.0, 0.0
    total = 0.0
    for i in range(1, len(ts)):
        gap = (ts[i] - ts[i - 1]).total_seconds()
        if gap <= umbral_min * 60:
            total += gap
    span = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
    return total / 3600, span / 3600


def horas_por_dia(eventos: pd.DataFrame,
                  medicos: list[str] | None = None,
                  departamentos: list[str] | None = None,
                  umbral_min: int = UMBRAL_MINUTOS) -> pd.DataFrame:
    d = eventos.copy()
    if medicos:
        d = d[d["medico"].isin(medicos)]
    if departamentos:
        d = d[d["departamento"].isin(departamentos)]
    if d.empty:
        return pd.DataFrame()

    filas = []
    for (med, dep, fecha), g in d.groupby(["medico", "departamento", "fecha"]):
        horas_act, span = _horas_activas(g["timestamp"], umbral_min)
        filas.append({
            "medico":          med,
            "departamento":    dep,
            "fecha":           fecha,
            "primera_atencion": g["timestamp"].min(),
            "ultima_atencion":  g["timestamp"].max(),
            "n_evoluciones":   int((g["fuente"] == "evolucion").sum()),
            "n_consultas":     int((g["fuente"] == "consulta").sum()),
            "horas_span":      span,
            "horas_muertas":   max(span - horas_act, 0.0),
            "horas":           horas_act,
        })

    res = pd.DataFrame(filas)
    # Redondeo a enteros
    for col in ("horas", "horas_span", "horas_muertas"):
        res[col] = res[col].round().astype(int)

    return res.sort_values(["medico", "departamento", "fecha"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    eventos = cargar_eventos()

    medicos       = sorted(eventos["medico"].dropna().unique().tolist())
    departamentos = sorted(eventos["departamento"].dropna().unique().tolist())

    medicos_sel = elegir_multi("Médicos disponibles", medicos)
    deps_sel    = elegir_multi("Departamentos disponibles", departamentos)

    res = horas_por_dia(eventos, medicos_sel, deps_sel)

    if res.empty:
        print("\nNo hay datos para la selección.")
        return

    print(f"\n=== Horas por día (enteras, huecos > {UMBRAL_MINUTOS} min descontados) ===")
    print(res.to_string(index=False))

    print("\n=== Totales por médico ===")
    total = (res.groupby("medico", as_index=False)
                .agg(horas=("horas", "sum"),
                     horas_muertas=("horas_muertas", "sum"))
                .sort_values("horas", ascending=False))
    print(total.to_string(index=False))

    salida = "horas_por_dia.csv"
    res.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"\nResultado guardado en: {salida}")


if __name__ == "__main__":
    main()
