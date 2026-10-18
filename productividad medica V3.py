import csv
import re
import pandas as pd

EVOLUCIONES_PATH = "medicos_evoluciones.csv"
CONSULTAS_PATH   = "Ingresos_Consultorios.csv"
CIRUGIAS_PATH    = "ReporteCirugiaUrosdesde031219.csv"

# Huecos mayores a este umbral se consideran "horas muertas" y no suman
# (aplica solo entre eventos puntuales; las cirugías se suman siempre completas).
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


def _parse_fecha_es(series: pd.Series) -> pd.Series:
    """Parsea fechas tipo '17/09/2026 5:30:00 p. m.'."""
    s = series.astype(str).str.strip()
    s = s.str.replace(r"p\.\s*m\.", "PM", regex=True, flags=re.IGNORECASE)
    s = s.str.replace(r"a\.\s*m\.", "AM", regex=True, flags=re.IGNORECASE)
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()
    return pd.to_datetime(s, format="%d/%m/%Y %I:%M:%S %p", errors="coerce")


# ---------------------------------------------------------------------------
# Carga de fuentes
# ---------------------------------------------------------------------------
def cargar_eventos() -> pd.DataFrame:
    """Une evoluciones + consultas en una sola tabla de eventos (puntos en el tiempo)."""
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


def cargar_cirugias() -> pd.DataFrame:
    """
    Carga cirugías y retorna intervalos de ocupación por médico AYUDANTE:
        medico, departamento, fecha, inicio, fin
    - medico        = nombre_ayudante
    - departamento  = especialidad (fallback: 'CIRUGIA')
    - fecha         = día de hora_inicio
    """
    vacio = pd.DataFrame(columns=["medico", "departamento", "fecha", "inicio", "fin"])
    try:
        ci = _leer_tsv(CIRUGIAS_PATH)
    except FileNotFoundError:
        print(f"[aviso] No se encontró {CIRUGIAS_PATH}; se omite ocupación por cirugías.")
        return vacio

    if "nombre_ayudante" not in ci.columns:
        print("[aviso] El archivo de cirugías no contiene 'nombre_ayudante'.")
        return vacio

    ci["inicio"] = _parse_fecha_es(ci["hora_inicio"])
    ci["fin"]    = _parse_fecha_es(ci["hora_fin"])

    # Departamento = especialidad de la cirugía (fallback genérico)
    esp = ci.get("especialidad", pd.Series([""] * len(ci), index=ci.index))
    esp = esp.fillna("").astype(str).str.strip()
    ci["departamento"] = esp.where(esp != "", "CIRUGIA")

    # Médico ayudante
    ci["medico"] = ci["nombre_ayudante"].fillna("").astype(str).str.strip()

    # Limpieza
    ci = ci.dropna(subset=["inicio", "fin"])
    ci = ci[ci["medico"] != ""]
    ci = ci[ci["fin"] >= ci["inicio"]]
    ci["fecha"] = ci["inicio"].dt.date

    return ci[["medico", "departamento", "fecha", "inicio", "fin"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Selección múltiple por consola
# ---------------------------------------------------------------------------
def _parsear_seleccion(texto: str, n: int) -> list[int] | None:
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
# Cálculo de horas activas descontando huecos + cirugías (ayudante)
# ---------------------------------------------------------------------------
def _intervalos_desde_eventos(ts_series: pd.Series, umbral_min: int):
    """Intervalos entre eventos consecutivos con hueco <= umbral."""
    ts = ts_series.sort_values().reset_index(drop=True)
    intervals = []
    for i in range(1, len(ts)):
        gap = (ts[i] - ts[i - 1]).total_seconds()
        if gap <= umbral_min * 60:
            intervals.append((ts[i - 1], ts[i]))
    return intervals


def _merge_intervalos(intervals):
    """Fusiona intervalos solapados (evita doble conteo con cirugías)."""
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x[0])
    merged = [list(intervals[0])]
    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged


def horas_por_dia(eventos: pd.DataFrame,
                  cirugias: pd.DataFrame | None = None,
                  medicos: list[str] | None = None,
                  departamentos: list[str] | None = None,
                  umbral_min: int = UMBRAL_MINUTOS) -> pd.DataFrame:
    d = eventos.copy()
    if medicos:
        d = d[d["medico"].isin(medicos)]
    if departamentos:
        d = d[d["departamento"].isin(departamentos)]

    if cirugias is None:
        c = pd.DataFrame(columns=["medico", "departamento", "fecha", "inicio", "fin"])
    else:
        c = cirugias.copy()
        if medicos:
            c = c[c["medico"].isin(medicos)]
        if departamentos:
            c = c[c["departamento"].isin(departamentos)]

    if d.empty and c.empty:
        return pd.DataFrame()

    # Claves (médico, depto, fecha) presentes en cualquiera de las dos fuentes
    keys: set = set()
    if not d.empty:
        keys.update(d[["medico", "departamento", "fecha"]]
                    .itertuples(index=False, name=None))
    if not c.empty:
        keys.update(c[["medico", "departamento", "fecha"]]
                    .itertuples(index=False, name=None))

    filas = []
    for med, dep, fecha in sorted(keys):
        eg = d[(d["medico"] == med) &
               (d["departamento"] == dep) &
               (d["fecha"] == fecha)] if not d.empty else d
        cg = c[(c["medico"] == med) &
               (c["departamento"] == dep) &
               (c["fecha"] == fecha)] if not c.empty else c

        # Intervalos "activos": huecos entre eventos + cirugías completas
        intervals: list[tuple] = []
        if not eg.empty:
            intervals.extend(_intervalos_desde_eventos(eg["timestamp"], umbral_min))
        for _, row in cg.iterrows():
            intervals.append((row["inicio"], row["fin"]))

        # Span = primer a último timestamp (eventos + cirugías)
        all_ts = []
        if not eg.empty:
            all_ts.extend(eg["timestamp"].tolist())
        if not cg.empty:
            all_ts.extend(cg["inicio"].tolist())
            all_ts.extend(cg["fin"].tolist())
        if not all_ts:
            continue

        span = (max(all_ts) - min(all_ts)).total_seconds() / 3600

        if intervals:
            merged = _merge_intervalos(intervals)
            horas_act = sum((e - s).total_seconds() for s, e in merged) / 3600
        else:
            horas_act = 0.0

        filas.append({
            "medico":           med,
            "departamento":     dep,
            "fecha":            fecha,
            "primera_atencion": min(all_ts),
            "ultima_atencion":  max(all_ts),
            "n_evoluciones":    int((eg["fuente"] == "evolucion").sum()) if not eg.empty else 0,
            "n_consultas":      int((eg["fuente"] == "consulta").sum())   if not eg.empty else 0,
            "n_cirugias":       int(len(cg)),
            "horas_span":       span,
            "horas_muertas":    max(span - horas_act, 0.0),
            "horas":            horas_act,
        })

    res = pd.DataFrame(filas)
    for col in ("horas", "horas_span", "horas_muertas"):
        res[col] = res[col].round().astype(int)

    return res.sort_values(["medico", "departamento", "fecha"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    eventos  = cargar_eventos()
    cirugias = cargar_cirugias()

    medicos = sorted(
        set(eventos["medico"].dropna().unique().tolist())
        | set(cirugias["medico"].dropna().unique().tolist())
    )
    departamentos = sorted(
        set(eventos["departamento"].dropna().unique().tolist())
        | set(cirugias["departamento"].dropna().unique().tolist())
    )

    medicos_sel = elegir_multi("Médicos disponibles", medicos)
    deps_sel    = elegir_multi("Departamentos disponibles", departamentos)

    res = horas_por_dia(eventos, cirugias, medicos_sel, deps_sel)

    if res.empty:
        print("\nNo hay datos para la selección.")
        return

    print(f"\n=== Horas por día (enteras, huecos > {UMBRAL_MINUTOS} min descontados) ===")
    print("    Incluye ocupación por cirugías como ayudante (hora_fin - hora_inicio)")
    print(res.to_string(index=False))

    print("\n=== Totales por médico ===")
    total = (res.groupby("medico", as_index=False)
                .agg(horas=("horas", "sum"),
                     horas_muertas=("horas_muertas", "sum"),
                     n_cirugias=("n_cirugias", "sum"))
                .sort_values("horas", ascending=False))
    print(total.to_string(index=False))

    salida = "horas_por_dia.csv"
    res.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"\nResultado guardado en: {salida}")


if __name__ == "__main__":
    main()
