"""
=============================================================================
 LABORATORIO  --  barrido de parametros con validacion honesta
=============================================================================

 EL PROBLEMA QUE RESUELVE
 ------------------------
 Si pruebas 200 combinaciones sobre los mismos datos y te quedas con la
 mejor, casi seguro has encontrado ruido, no una ventaja. Con suficientes
 intentos siempre aparece algo que "funciona" en el pasado.

 LA DEFENSA
 ----------
 Partimos el historico en dos tramos que no se mezclan:

   DISENYO   2015-2021  ->  aqui se prueban todas las combinaciones
   VALIDACION 2022-2026 ->  aqui solo se prueban las 5 finalistas, UNA VEZ

 Una configuracion solo es creible si aguanta en el segundo tramo, que
 nunca influyo en su seleccion. Si funciona en disenyo pero se cae en
 validacion, era sobreajuste.

 REGLA DE ORO: el tramo de validacion se mira una sola vez. Si lo usas
 para reajustar, deja de ser validacion y vuelves al punto de partida.
=============================================================================
"""

import itertools
import json
import os
import sys

import pandas as pd

from motor import BASE, Motor, recortar
from backtest_v1 import obtener_universo, descargar

CACHE = os.path.join(os.path.dirname(__file__), "cache_precios.parquet")

FIN_DISENYO = "2021-12-31"
INI_VALIDACION = "2022-01-01"
INICIO = "2014-01-01"


# ---------------------------------------------------------------------------
#  Datos: se descargan una vez y se reutilizan
# ---------------------------------------------------------------------------

def cargar_datos():
    if os.path.exists(CACHE):
        print("Leyendo precios de la cache...")
        panel = pd.read_parquet(CACHE)
    else:
        print("Descargando precios (solo la primera vez)...")
        universo = obtener_universo()
        print(f"  {len(universo)} valores en el universo")
        datos = descargar(universo, INICIO, None)
        print(f"  {len(datos)} descargados")
        panel = pd.concat(datos, names=["ticker", "fecha"])
        panel.to_parquet(CACHE)
        print(f"  Cache guardada en {CACHE}")

    datos = {t: panel.loc[t] for t in panel.index.get_level_values(0).unique()}
    bench = datos.pop("SPY", None)
    if bench is None:
        bench = descargar(["SPY"], INICIO, None)["SPY"]
    return datos, bench


# ---------------------------------------------------------------------------
#  Rejilla de combinaciones
# ---------------------------------------------------------------------------

def rejilla():
    """Cada variante ataca una de las causas del fallo de v1.

    - rsi_entrada mas bajo  -> menos operaciones, entradas mas selectivas
    - stop mas cerrado      -> reduce la perdida media (era 29 vs 17 de ganancia)
    - salidas mas lentas    -> deja correr las ganadoras
    """
    variantes_salida = [
        # (etiqueta, usar_rsi, sma_salida, trailing_atr, objetivo_R)
        ("rsi70",         True,  None, None, None),
        ("rsi80",         True,  None, None, None),
        ("sma20",         False, 20,   None, None),
        ("trailing_2atr", False, None, 2.0,  None),
        ("trailing_3atr", False, None, 3.0,  None),
        ("objetivo_2R",   False, None, None, 2.0),
        ("objetivo_3R",   False, None, None, 3.0),
    ]

    combos = []
    for (etq, usar_rsi, sma_sal, trail, objR), rsi_ent, stop, dias in itertools.product(
        variantes_salida, [15, 25], [1.5, 2.5], [10, 25]
    ):
        cfg = dict(BASE)
        cfg.update({
            "rsi_entrada": rsi_ent,
            "atr_multiplo_stop": stop,
            "max_dias_posicion": dias,
            "usar_rsi_salida": usar_rsi,
            "rsi_salida": 80 if etq == "rsi80" else 70,
            "sma_salida": sma_sal,
            "trailing_atr": trail,
            "objetivo_R": objR,
        })
        combos.append((f"{etq}|rsi{rsi_ent}|stop{stop}|d{dias}", cfg))
    return combos


# ---------------------------------------------------------------------------
#  Evaluacion
# ---------------------------------------------------------------------------

def evaluar(cfg, datos, bench, ini, fin):
    d = recortar(datos, ini, fin)
    b = bench.loc[(bench.index >= pd.Timestamp(ini) - pd.Timedelta(days=400))
                  & (bench.index <= pd.Timestamp(fin))]
    cal = b.loc[b.index >= pd.Timestamp(ini)].index
    if len(cal) < 50:
        return None
    m, _, _ = Motor(d, b, cfg).ejecutar(cal)
    return m


def puntuar(m):
    """Prioriza robustez, no rentabilidad bruta.

    Exige un minimo de operaciones (una muestra pequenya no demuestra nada)
    y penaliza el drawdown. Un sistema rentable que cae un 40% no se opera:
    lo abandonas antes de que se recupere.
    """
    if m is None or m["ops"] < 60:
        return -99.0
    if m["dd"] < -0.30:
        return -99.0
    return m["cagr"] * 100 + m["pf"] * 5 + m["dd"] * 40


def main():
    datos, bench = cargar_datos()
    print(f"\nValores disponibles: {len(datos)}")

    combos = rejilla()
    print(f"Combinaciones a probar: {len(combos)}")
    print(f"Disenyo: {INICIO} a {FIN_DISENYO}")
    print(f"Validacion: {INI_VALIDACION} en adelante (intocable hasta el final)\n")

    # ---------------- FASE 1: disenyo ----------------
    print("=" * 78)
    print(" FASE 1 - BARRIDO SOBRE EL TRAMO DE DISENYO")
    print("=" * 78)
    print(f"{'configuracion':<34}{'ops':>6}{'CAGR':>9}{'DD':>8}{'PF':>7}{'win':>7}{'R':>7}")
    print("-" * 78)

    resultados = []
    for i, (nombre, cfg) in enumerate(combos, 1):
        m = evaluar(cfg, datos, bench, "2015-01-01", FIN_DISENYO)
        if m:
            s = puntuar(m)
            resultados.append((s, nombre, cfg, m))
            if s > -99:
                print(f"{nombre:<34}{m['ops']:>6}{m['cagr']*100:>8.1f}%"
                      f"{m['dd']*100:>7.1f}%{m['pf']:>7.2f}{m['win']*100:>6.1f}%{m['R']:>7.2f}")
        sys.stdout.flush()
        if i % 10 == 0:
            print(f"   ... {i}/{len(combos)}")

    resultados.sort(key=lambda x: x[0], reverse=True)
    finalistas = [r for r in resultados if r[0] > -99][:5]

    if not finalistas:
        print("\nNinguna configuracion supera los minimos exigidos.")
        print("Conclusion: este estilo de estrategia no funciona en este universo.")
        print("Siguiente paso: cambiar de enfoque (momentum con holds largos).")
        return

    # ---------------- FASE 2: validacion ----------------
    print("\n" + "=" * 78)
    print(" FASE 2 - VALIDACION EN DATOS NUNCA VISTOS")
    print("=" * 78)
    print(f"{'configuracion':<34}{'ops':>6}{'CAGR':>9}{'DD':>8}{'PF':>7}{'win':>7}")
    print("-" * 78)

    veredictos = []
    for _, nombre, cfg, m_dis in finalistas:
        m_val = evaluar(cfg, datos, bench, INI_VALIDACION, "2026-12-31")
        if m_val:
            print(f"{nombre:<34}{m_val['ops']:>6}{m_val['cagr']*100:>8.1f}%"
                  f"{m_val['dd']*100:>7.1f}%{m_val['pf']:>7.2f}{m_val['win']*100:>6.1f}%")
            veredictos.append({
                "nombre": nombre,
                "disenyo": {k: round(float(v), 4) for k, v in m_dis.items()},
                "validacion": {k: round(float(v), 4) for k, v in m_val.items()},
                "config": {k: v for k, v in cfg.items()},
            })

    # ---------------- VEREDICTO ----------------
    print("\n" + "=" * 78)
    print(" VEREDICTO")
    print("=" * 78)

    solidas = [v for v in veredictos
               if v["validacion"]["pf"] > 1.3 and v["validacion"]["dd"] > -0.20]

    if solidas:
        mejor = max(solidas, key=lambda v: v["validacion"]["cagr"])
        print(f" {len(solidas)} configuracion(es) aguantan fuera de muestra.")
        print(f" Mejor: {mejor['nombre']}")
        print(f"   Disenyo    -> CAGR {mejor['disenyo']['cagr']*100:.1f}%  "
              f"PF {mejor['disenyo']['pf']:.2f}  DD {mejor['disenyo']['dd']*100:.1f}%")
        print(f"   Validacion -> CAGR {mejor['validacion']['cagr']*100:.1f}%  "
              f"PF {mejor['validacion']['pf']:.2f}  DD {mejor['validacion']['dd']*100:.1f}%")
        print("\n Si ambos tramos se parecen, la ventaja es plausible.")
        print(" Si el segundo es mucho peor, sigue siendo sobreajuste.")
    else:
        print(" Ninguna configuracion supera el filtro de validacion.")
        print(" (se exigia PF > 1.3 y caida maxima menor del 20%)")
        print("\n Conclusion honesta: la reversion a la media en grandes")
        print(" capitalizaciones USA no ofrece ventaja suficiente para cubrir")
        print(" costes. Conviene cambiar de estilo antes que seguir ajustando.")

    ruta = os.path.join(os.path.dirname(__file__), "..", "public", "data", "lab.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(veredictos, f, indent=2, ensure_ascii=False)
    print(f"\n Detalle completo guardado en public/data/lab.json")


if __name__ == "__main__":
    main()
