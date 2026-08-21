"""
=============================================================================
 LABORATORIO MOMENTUM  --  misma validacion honesta, otra estrategia
=============================================================================

 Mismo protocolo que el laboratorio anterior:
   DISENYO    2015-2021  ->  se prueban todas las combinaciones
   VALIDACION 2022-2026  ->  solo las finalistas, una sola vez

 AnyADIDO IMPORTANTE: aqui comparamos SIEMPRE contra comprar y mantener
 el SPY en el mismo periodo. En el laboratorio anterior descubrimos que
 la mejor configuracion (8.8% anual) ni siquiera llegaba al indice (~13%).
 Batir al indice ajustando por riesgo es el listón real, no ganar dinero.
=============================================================================
"""

import itertools
import json
import os
import sys

import pandas as pd

from momentum import BASE_MOM, MotorMomentum, construir_paneles
from lab import cargar_datos

FIN_DISENYO = "2021-12-31"
INI_VALIDACION = "2022-01-01"


def rejilla():
    """Cada eje ataca una decision distinta del disenyo."""
    combos = []
    for lookback, n, colchon, pond, regimen in itertools.product(
        [126, 252],            # ventana de fuerza: 6 o 12 meses
        [5, 10, 15],           # cuantos valores en cartera
        [1.0, 1.5],            # colchon de rotacion
        ["igual", "inv_vol"],  # ponderacion
        [True, False],         # filtro de regimen de mercado
    ):
        cfg = dict(BASE_MOM)
        cfg.update({"lookback": lookback, "n_cartera": n, "colchon": colchon,
                    "ponderacion": pond, "usar_regimen": regimen})
        etq = (f"{lookback//21}m|n{n}|c{colchon}|{pond[:4]}"
               f"|{'reg' if regimen else 'sinreg'}")
        combos.append((etq, cfg))
    return combos


def evaluar(cfg, cierres, volumenes, bench, ini, fin):
    margen = pd.Timestamp(ini) - pd.Timedelta(days=500)
    c = cierres.loc[(cierres.index >= margen) & (cierres.index <= pd.Timestamp(fin))]
    v = volumenes.loc[c.index]
    b = bench.loc[(bench.index >= margen) & (bench.index <= pd.Timestamp(fin))]
    cal = c.index[c.index >= pd.Timestamp(ini)]
    cal = cal.intersection(b.index)
    if len(cal) < 100:
        return None
    return MotorMomentum(c, v, b, cfg).ejecutar(cal)[0]


def rentabilidad_indice(bench, ini, fin):
    b = bench["Close"]
    b = b.loc[(b.index >= pd.Timestamp(ini)) & (b.index <= pd.Timestamp(fin))]
    if len(b) < 30:
        return 0.0, 0.0
    anyos = (b.index[-1] - b.index[0]).days / 365.25
    cagr = (b.iloc[-1] / b.iloc[0]) ** (1 / anyos) - 1
    dd = float((b / b.cummax() - 1).min())
    return float(cagr), dd


def puntuar(m):
    if m is None or m["ops"] < 20:
        return -99.0
    if m["dd"] < -0.35:
        return -99.0
    # Rentabilidad penalizada por caida: premia la robustez, no el pico
    return m["cagr"] * 100 + m["dd"] * 60


def main():
    datos, bench = cargar_datos()
    cierres, volumenes = construir_paneles(datos)
    print(f"\nPanel construido: {cierres.shape[1]} valores, {cierres.shape[0]} sesiones")

    combos = rejilla()
    print(f"Combinaciones: {len(combos)}\n")

    spy_dis = rentabilidad_indice(bench, "2015-01-01", FIN_DISENYO)
    spy_val = rentabilidad_indice(bench, INI_VALIDACION, "2026-12-31")
    print(f"Referencia SPY  disenyo: {spy_dis[0]*100:5.1f}% anual  "
          f"(caida {spy_dis[1]*100:.1f}%)")
    print(f"Referencia SPY  validac: {spy_val[0]*100:5.1f}% anual  "
          f"(caida {spy_val[1]*100:.1f}%)\n")

    print("=" * 76)
    print(" FASE 1 - DISENYO (2015-2021)")
    print("=" * 76)
    print(f"{'configuracion':<30}{'ops':>6}{'op/anyo':>9}{'CAGR':>9}{'DD':>8}{'Sharpe':>8}")
    print("-" * 76)

    resultados = []
    for i, (nombre, cfg) in enumerate(combos, 1):
        m = evaluar(cfg, cierres, volumenes, bench, "2015-01-01", FIN_DISENYO)
        if m:
            resultados.append((puntuar(m), nombre, cfg, m))
            print(f"{nombre:<30}{m['ops']:>6}{m['rot']:>9.0f}"
                  f"{m['cagr']*100:>8.1f}%{m['dd']*100:>7.1f}%{m['sharpe']:>8.2f}")
        sys.stdout.flush()

    resultados.sort(key=lambda x: x[0], reverse=True)
    finalistas = [r for r in resultados if r[0] > -99][:5]
    if not finalistas:
        print("\nNinguna configuracion alcanza los minimos.")
        return

    print("\n" + "=" * 76)
    print(" FASE 2 - VALIDACION (2022-2026, datos nunca vistos)")
    print("=" * 76)
    print(f"{'configuracion':<30}{'ops':>6}{'op/anyo':>9}{'CAGR':>9}{'DD':>8}{'Sharpe':>8}")
    print("-" * 76)

    veredictos = []
    for _, nombre, cfg, m_dis in finalistas:
        m_val = evaluar(cfg, cierres, volumenes, bench, INI_VALIDACION, "2026-12-31")
        if m_val:
            print(f"{nombre:<30}{m_val['ops']:>6}{m_val['rot']:>9.0f}"
                  f"{m_val['cagr']*100:>8.1f}%{m_val['dd']*100:>7.1f}%{m_val['sharpe']:>8.2f}")
            veredictos.append({"nombre": nombre,
                               "disenyo": {k: round(float(v), 4) for k, v in m_dis.items()},
                               "validacion": {k: round(float(v), 4) for k, v in m_val.items()},
                               "config": cfg})

    print("\n" + "=" * 76)
    print(" VEREDICTO")
    print("=" * 76)
    print(f" El listón es el SPY: {spy_val[0]*100:.1f}% anual con caida "
          f"{spy_val[1]*100:.1f}% en validacion.\n")

    baten = [v for v in veredictos
             if v["validacion"]["cagr"] > spy_val[0]
             and v["validacion"]["dd"] > spy_val[1]]

    consistentes = [v for v in veredictos
                    if v["validacion"]["cagr"] > 0
                    and abs(v["validacion"]["cagr"] - v["disenyo"]["cagr"]) < 0.10]

    if baten:
        mejor = max(baten, key=lambda v: v["validacion"]["sharpe"])
        print(f" {len(baten)} configuracion(es) baten al indice con menos caida.")
        print(f" Mejor: {mejor['nombre']}")
        print(f"   Disenyo    -> CAGR {mejor['disenyo']['cagr']*100:5.1f}%  "
              f"DD {mejor['disenyo']['dd']*100:6.1f}%  "
              f"Sharpe {mejor['disenyo']['sharpe']:.2f}  "
              f"{mejor['disenyo']['rot']:.0f} op/anyo")
        print(f"   Validacion -> CAGR {mejor['validacion']['cagr']*100:5.1f}%  "
              f"DD {mejor['validacion']['dd']*100:6.1f}%  "
              f"Sharpe {mejor['validacion']['sharpe']:.2f}  "
              f"{mejor['validacion']['rot']:.0f} op/anyo")
    elif consistentes:
        print(" Ninguna bate al indice, pero hay configuraciones consistentes")
        print(" entre ambos tramos. La estrategia funciona; simplemente no")
        print(" aporta sobre comprar el indice y esperar.")
    else:
        print(" Ninguna configuracion bate al indice ni se comporta de forma")
        print(" consistente entre ambos tramos.")
        print("\n Conclusion honesta: con este universo, este capital y estos")
        print(" costes, la opcion racional es un indice con aportaciones")
        print(" periodicas. Vale la pena haberlo comprobado con datos propios.")

    # ---------------- FASE 3: efecto del take profit ----------------
    # Se aplica sobre la configuracion ya ganadora, en lugar de multiplicar
    # la rejilla. Probar menos combinaciones reduce el riesgo de que el
    # resultado sea casualidad.
    print("\n" + "=" * 76)
    print(" FASE 3 - EFECTO DEL TAKE PROFIT Y DEL STOP CATASTROFICO")
    print("=" * 76)

    _, nombre_base, cfg_base, _ = finalistas[0]
    print(f" Configuracion de partida: {nombre_base}\n")
    print(f"{'variante':<26}{'ops':>6}{'op/anyo':>9}{'CAGR':>9}{'DD':>8}{'Sharpe':>8}{'dias':>7}")
    print("-" * 76)

    variantes = [
        ("sin take profit",   {"take_profit": None,  "stop_catastrofe": None}),
        ("TP +15%",           {"take_profit": 0.15,  "stop_catastrofe": None}),
        ("TP +25%",           {"take_profit": 0.25,  "stop_catastrofe": None}),
        ("TP +40%",           {"take_profit": 0.40,  "stop_catastrofe": None}),
        ("stop -25%",         {"take_profit": None,  "stop_catastrofe": -0.25}),
        ("stop -35%",         {"take_profit": None,  "stop_catastrofe": -0.35}),
        ("TP +40% y stop -25%", {"take_profit": 0.40, "stop_catastrofe": -0.25}),
    ]

    tabla_tp = []
    for etq, cambios in variantes:
        cfg = dict(cfg_base)
        cfg.update(cambios)
        # Se mide en AMBOS tramos: si el take profit ayudase solo en uno,
        # seria otra senyal de sobreajuste.
        m_d = evaluar(cfg, cierres, volumenes, bench, "2015-01-01", FIN_DISENYO)
        m_v = evaluar(cfg, cierres, volumenes, bench, INI_VALIDACION, "2026-12-31")
        if m_d and m_v:
            print(f"{etq:<26}{m_v['ops']:>6}{m_v['rot']:>9.0f}"
                  f"{m_v['cagr']*100:>8.1f}%{m_v['dd']*100:>7.1f}%"
                  f"{m_v['sharpe']:>8.2f}{m_v['dias']:>7.0f}")
            tabla_tp.append({"variante": etq,
                             "disenyo": {k: round(float(v), 4) for k, v in m_d.items()},
                             "validacion": {k: round(float(v), 4) for k, v in m_v.items()}})
        sys.stdout.flush()

    if tabla_tp:
        base = next((t for t in tabla_tp if t["variante"] == "sin take profit"), None)
        mejor_tp = max(tabla_tp, key=lambda t: t["validacion"]["sharpe"])
        print()
        if base and mejor_tp["variante"] == "sin take profit":
            print(" El take profit NO mejora nada: la mejor variante es no usarlo.")
            print(" Coincide con la teoria: cortar ganadoras destruye el momentum.")
        elif base:
            dif = mejor_tp["validacion"]["sharpe"] - base["validacion"]["sharpe"]
            print(f" La mejor variante es '{mejor_tp['variante']}' "
                  f"(Sharpe {dif:+.2f} frente a no usarlo).")
            print(" Comprueba que tambien gane en el tramo de disenyo antes de fiarte.")

    ruta = os.path.join(os.path.dirname(__file__), "..", "public", "data", "lab_momentum.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"spy_disenyo": spy_dis, "spy_validacion": spy_val,
                   "resultados": veredictos, "take_profit": tabla_tp},
                  f, indent=2, ensure_ascii=False)
    print(f"\n Detalle en public/data/lab_momentum.json")


if __name__ == "__main__":
    main()
