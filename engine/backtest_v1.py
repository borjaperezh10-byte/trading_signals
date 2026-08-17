"""
=============================================================================
 MOTOR DE BACKTEST v1  --  Estrategia "Pullback en Tendencia Alcista"
=============================================================================

 QUE HACE ESTE ARCHIVO
 ---------------------
 Simula, sobre datos historicos reales, que habria pasado si hubieras
 aplicado mecanicamente estas reglas durante los ultimos anyos.

 No predice el futuro. Mide si la logica tiene ventaja estadistica.

 REGLAS IMPLEMENTADAS
 --------------------
 Universo .... S&P 500 + Nasdaq 100 (~520 valores tras deduplicar)
 Regimen ..... Solo se compra si SPY > SMA200
 Entrada ..... Precio > SMA200  Y  SMA50 > SMA200  Y  RSI(4) < 30
 Ranking ..... Mayor fuerza relativa a 6 meses (ROC 126 sesiones)
 Salida ...... Stop 2.5*ATR  |  RSI(4) > 65 o cierre > SMA10  |  15 dias
 Riesgo ...... 1% del capital por operacion, max 5 posiciones simultaneas

 COMO SE EJECUTAN LAS ORDENES
 ----------------------------
 Las senyales se calculan con el CIERRE del dia t y se ejecutan en la
 APERTURA del dia t+1. Esto evita el "lookahead bias": mirar datos que
 en el momento real no habrias tenido. Es el error nº1 en backtesting
 y hace que sistemas malos parezcan brillantes.
=============================================================================
"""

import numpy as np
import pandas as pd

# ============================================================================
#  CONFIGURACION  --  toca solo estos valores para experimentar
# ============================================================================

CONFIG = {
    # --- Capital y riesgo ---
    "capital_inicial":      5000.0,   # EUR/USD de partida
    "riesgo_por_op":        0.01,     # 1% del capital arriesgado por operacion
    "max_posiciones":       5,        # posiciones simultaneas maximas
    "max_peso_posicion":    0.20,     # ninguna posicion supera el 20% del capital

    # --- Entrada ---
    "sma_larga":            200,      # tendencia mayor
    "sma_media":            50,       # tendencia intermedia
    "rsi_periodo":          4,        # RSI corto para detectar el pullback
    "rsi_entrada":          30,       # umbral de sobreventa
    "roc_ranking":          126,      # ~6 meses, para ordenar candidatos

    # --- Salida ---
    "atr_periodo":          14,
    "atr_multiplo_stop":    2.5,      # distancia del stop en ATRs
    "rsi_salida":           65,       # sobrecompra -> cerrar
    "sma_salida":           10,       # cierre por encima de SMA10 -> cerrar
    "max_dias_posicion":    15,       # salida por tiempo

    # --- Filtros de liquidez ---
    "precio_minimo":        10.0,     # descarta chicharros
    "volumen_dolar_min":    10_000_000,  # 10M$ diarios de media (20d)

    # --- Costes reales (por operacion, cada lado) ---
    "comision_pct":         0.0010,   # 0.10%
    "slippage_pct":         0.0005,   # 0.05%
}


# ============================================================================
#  INDICADORES TECNICOS
#  Implementados a mano para no depender de librerias externas.
# ============================================================================

def rsi(serie: pd.Series, periodo: int) -> pd.Series:
    """RSI de Wilder. Oscila 0-100. Bajo = sobrevendido."""
    delta = serie.diff()
    ganancia = delta.clip(lower=0)
    perdida = -delta.clip(upper=0)
    media_g = ganancia.ewm(alpha=1 / periodo, adjust=False).mean()
    media_p = perdida.ewm(alpha=1 / periodo, adjust=False).mean()
    rs = media_g / media_p.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df: pd.DataFrame, periodo: int) -> pd.Series:
    """Average True Range: cuanto se mueve el precio en un dia tipico.
    Es la base del stop: un stop debe respetar el ruido normal del valor."""
    alto_bajo = df["High"] - df["Low"]
    alto_cierre = (df["High"] - df["Close"].shift()).abs()
    bajo_cierre = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([alto_bajo, alto_cierre, bajo_cierre], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / periodo, adjust=False).mean()


def preparar_indicadores(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Anyade todas las columnas derivadas que necesita la estrategia."""
    d = df.copy()
    d["sma_larga"] = d["Close"].rolling(cfg["sma_larga"]).mean()
    d["sma_media"] = d["Close"].rolling(cfg["sma_media"]).mean()
    d["sma_salida"] = d["Close"].rolling(cfg["sma_salida"]).mean()
    d["rsi"] = rsi(d["Close"], cfg["rsi_periodo"])
    d["atr"] = atr(d, cfg["atr_periodo"])
    d["roc"] = d["Close"].pct_change(cfg["roc_ranking"]) * 100
    d["vol_dolar"] = (d["Close"] * d["Volume"]).rolling(20).mean()

    # --- Senyal de ENTRADA (evaluada al cierre) ---
    d["senal_entrada"] = (
        (d["Close"] > d["sma_larga"])          # tendencia mayor alcista
        & (d["sma_media"] > d["sma_larga"])    # estructura alcista confirmada
        & (d["rsi"] < cfg["rsi_entrada"])      # retroceso de corto plazo
        & (d["Close"] > cfg["precio_minimo"])  # liquidez: precio
        & (d["vol_dolar"] > cfg["volumen_dolar_min"])  # liquidez: volumen
        & (d["atr"] > 0)
    )

    # --- Senyal de SALIDA por objetivo (evaluada al cierre) ---
    d["senal_salida"] = (
        (d["rsi"] > cfg["rsi_salida"]) | (d["Close"] > d["sma_salida"])
    )
    return d


# ============================================================================
#  MOTOR DE BACKTEST
# ============================================================================

class Backtest:
    def __init__(self, datos: dict, benchmark: pd.DataFrame, cfg: dict):
        """
        datos     : dict {ticker: DataFrame con OHLCV}
        benchmark : DataFrame del SPY, para el filtro de regimen
        """
        self.cfg = cfg
        self.datos = {t: preparar_indicadores(d, cfg) for t, d in datos.items()}

        # Filtro de regimen de mercado sobre el benchmark
        bench = benchmark.copy()
        bench["sma200"] = bench["Close"].rolling(200).mean()
        bench["regimen_ok"] = bench["Close"] > bench["sma200"]
        self.benchmark = bench

        # Estado de la simulacion
        self.cash = cfg["capital_inicial"]
        self.posiciones = {}     # ticker -> dict con datos de la posicion
        self.operaciones = []    # historial cerrado
        self.curva = []          # equity dia a dia

    # ---- utilidades de coste -------------------------------------------
    def _precio_compra(self, p):
        """El precio real de compra es peor que el teorico: slippage."""
        return p * (1 + self.cfg["slippage_pct"])

    def _precio_venta(self, p):
        return p * (1 - self.cfg["slippage_pct"])

    def _comision(self, importe):
        return importe * self.cfg["comision_pct"]

    # ---- bucle principal ------------------------------------------------
    def ejecutar(self, calendario: pd.DatetimeIndex):
        cfg = self.cfg

        for i in range(1, len(calendario)):
            hoy = calendario[i]
            ayer = calendario[i - 1]

            # ============ 1. GESTIONAR SALIDAS ============
            for ticker in list(self.posiciones.keys()):
                pos = self.posiciones[ticker]
                d = self.datos[ticker]
                if hoy not in d.index:
                    continue

                barra = d.loc[hoy]
                salida_precio = None
                motivo = None

                # (a) Stop: prioridad absoluta. Si abre por debajo, gap.
                if barra["Open"] <= pos["stop"]:
                    salida_precio, motivo = barra["Open"], "stop_gap"
                elif barra["Low"] <= pos["stop"]:
                    salida_precio, motivo = pos["stop"], "stop"
                # (b) Objetivo alcanzado ayer -> vender en apertura de hoy
                elif ayer in d.index and bool(d.loc[ayer, "senal_salida"]):
                    salida_precio, motivo = barra["Open"], "objetivo"
                # (c) Tiempo agotado
                elif pos["dias"] >= cfg["max_dias_posicion"]:
                    salida_precio, motivo = barra["Open"], "tiempo"

                if salida_precio is not None:
                    p = self._precio_venta(salida_precio)
                    bruto = p * pos["acciones"]
                    self.cash += bruto - self._comision(bruto)
                    self.operaciones.append({
                        "ticker": ticker,
                        "entrada_fecha": pos["fecha"],
                        "salida_fecha": hoy,
                        "entrada": pos["precio"],
                        "salida": p,
                        "acciones": pos["acciones"],
                        "pnl": (p - pos["precio"]) * pos["acciones"],
                        "pnl_pct": (p / pos["precio"] - 1) * 100,
                        "dias": pos["dias"],
                        "motivo": motivo,
                        "riesgo_R": pos["riesgo_unitario"] * pos["acciones"],
                    })
                    del self.posiciones[ticker]
                else:
                    pos["dias"] += 1

            # ============ 2. VALORAR CARTERA ============
            valor = self.cash
            for ticker, pos in self.posiciones.items():
                d = self.datos[ticker]
                if hoy in d.index:
                    valor += d.loc[hoy, "Close"] * pos["acciones"]
                else:
                    valor += pos["precio"] * pos["acciones"]
            self.curva.append({"fecha": hoy, "equity": valor})

            # ============ 3. FILTRO DE REGIMEN ============
            if ayer not in self.benchmark.index:
                continue
            if not bool(self.benchmark.loc[ayer, "regimen_ok"]):
                continue  # mercado bajista: no se abren posiciones nuevas

            # ============ 4. BUSCAR ENTRADAS ============
            huecos = cfg["max_posiciones"] - len(self.posiciones)
            if huecos <= 0:
                continue

            candidatos = []
            for ticker, d in self.datos.items():
                if ticker in self.posiciones:
                    continue
                if ayer not in d.index or hoy not in d.index:
                    continue
                fila = d.loc[ayer]
                if bool(fila["senal_entrada"]) and not pd.isna(fila["roc"]):
                    candidatos.append((ticker, fila["roc"], fila["atr"]))

            # Ranking: mayor fuerza relativa primero
            candidatos.sort(key=lambda x: x[1], reverse=True)

            for ticker, _, atr_val in candidatos[:huecos]:
                barra = self.datos[ticker].loc[hoy]
                precio = self._precio_compra(barra["Open"])
                riesgo_unitario = cfg["atr_multiplo_stop"] * atr_val
                if riesgo_unitario <= 0:
                    continue

                # --- POSITION SIZING: la pieza clave del sistema ---
                # Todas las operaciones arriesgan lo mismo en euros.
                # Si el stop esta lejos (valor volatil), compramos menos.
                capital_riesgo = valor * cfg["riesgo_por_op"]
                acciones = int(capital_riesgo / riesgo_unitario)

                # Techo por concentracion
                max_importe = valor * cfg["max_peso_posicion"]
                acciones = min(acciones, int(max_importe / precio))

                coste = acciones * precio
                coste += self._comision(coste)
                if acciones < 1 or coste > self.cash:
                    continue

                self.cash -= coste
                self.posiciones[ticker] = {
                    "fecha": hoy,
                    "precio": precio,
                    "acciones": acciones,
                    "stop": barra["Open"] - riesgo_unitario,
                    "riesgo_unitario": riesgo_unitario,
                    "dias": 0,
                }

        return self._resultados()

    # ---- metricas -------------------------------------------------------
    def _resultados(self):
        curva = pd.DataFrame(self.curva).set_index("fecha")["equity"]
        ops = pd.DataFrame(self.operaciones)
        cfg = self.cfg

        if len(ops) == 0:
            return {"error": "Sin operaciones"}, curva, ops

        anyos = max((curva.index[-1] - curva.index[0]).days / 365.25, 0.01)
        cagr = (curva.iloc[-1] / cfg["capital_inicial"]) ** (1 / anyos) - 1
        drawdown = (curva / curva.cummax() - 1)

        ganadoras = ops[ops["pnl"] > 0]
        perdedoras = ops[ops["pnl"] <= 0]
        win_rate = len(ganadoras) / len(ops)
        gan_media = ganadoras["pnl"].mean() if len(ganadoras) else 0
        per_media = abs(perdedoras["pnl"].mean()) if len(perdedoras) else 0

        rets = curva.pct_change().dropna()
        sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0
        neg = rets[rets < 0]
        sortino = (rets.mean() / neg.std() * np.sqrt(252)) if len(neg) and neg.std() > 0 else 0

        # Ratio R medio: beneficio en multiplos del riesgo asumido
        ops = ops.copy()
        ops["R"] = ops["pnl"] / ops["riesgo_R"].replace(0, np.nan)

        m = {
            "Capital inicial":      f"{cfg['capital_inicial']:,.0f}",
            "Capital final":        f"{curva.iloc[-1]:,.0f}",
            "Rentabilidad total":   f"{(curva.iloc[-1]/cfg['capital_inicial']-1)*100:.1f}%",
            "CAGR":                 f"{cagr*100:.2f}%",
            "Max Drawdown":         f"{drawdown.min()*100:.1f}%",
            "Sharpe":               f"{sharpe:.2f}",
            "Sortino":              f"{sortino:.2f}",
            "Nº operaciones":       len(ops),
            "Win rate":             f"{win_rate*100:.1f}%",
            "Ganancia media":       f"{gan_media:,.0f}",
            "Perdida media":        f"{per_media:,.0f}",
            "Profit factor":        f"{ganadoras['pnl'].sum()/abs(perdedoras['pnl'].sum()):.2f}" if len(perdedoras) and perdedoras['pnl'].sum() != 0 else "inf",
            "Expectativa/op":       f"{ops['pnl'].mean():,.1f}",
            "Ratio R medio":        f"{ops['R'].mean():.2f}",
            "Dias medios":          f"{ops['dias'].mean():.1f}",
        }
        return m, curva, ops


# ============================================================================
#  DESCARGA DE DATOS  (requiere internet -- se ejecuta en Colab / GitHub)
# ============================================================================

def obtener_universo():
    """Lee los componentes del S&P 500 y del Nasdaq 100 desde Wikipedia."""
    sp500 = pd.read_html(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]["Symbol"].tolist()
    ndx = pd.read_html(
        "https://en.wikipedia.org/wiki/Nasdaq-100")[4]["Ticker"].tolist()
    universo = sorted(set([t.replace(".", "-") for t in sp500 + ndx]))
    return universo


def descargar(tickers, inicio, fin):
    """Descarga OHLCV con yfinance y devuelve un dict de DataFrames."""
    import yfinance as yf
    crudo = yf.download(tickers, start=inicio, end=fin,
                        auto_adjust=True, progress=True, threads=True)
    datos = {}
    for t in tickers:
        try:
            d = crudo.xs(t, axis=1, level=1).dropna()
            if len(d) > 250:          # al menos 1 anyo de historico
                datos[t] = d
        except (KeyError, ValueError):
            continue
    return datos


def main(inicio="2015-01-01", fin="2026-08-01"):
    print("Descargando universo...")
    universo = obtener_universo()
    print(f"  {len(universo)} valores")

    print("Descargando precios (esto tarda unos minutos)...")
    datos = descargar(universo, inicio, fin)
    print(f"  {len(datos)} valores con historico suficiente")

    print("Descargando benchmark SPY...")
    benchmark = descargar(["SPY"], inicio, fin)["SPY"]

    calendario = benchmark.index

    print("Ejecutando backtest...\n")
    bt = Backtest(datos, benchmark, CONFIG)
    metricas, curva, ops = bt.ejecutar(calendario)

    print("=" * 52)
    print(" RESULTADOS")
    print("=" * 52)
    for k, v in metricas.items():
        print(f" {k:.<26} {v}")
    print("=" * 52)

    # Comparativa contra comprar y mantener el indice
    bh = benchmark["Close"].iloc[-1] / benchmark["Close"].iloc[0] - 1
    print(f"\n Buy & Hold del SPY en el mismo periodo: {bh*100:.1f}%")

    ops.to_csv("operaciones.csv", index=False)
    curva.to_csv("curva_equity.csv")
    print("\n Guardados: operaciones.csv y curva_equity.csv")
    return metricas, curva, ops


if __name__ == "__main__":
    main()
