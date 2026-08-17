import datos from "../public/data/results.json";
import type { Resultados } from "../lib/tipos";

const r = datos as unknown as Resultados;

/* ------------------------------------------------------------------ */
/*  Utilidades de formato                                              */
/* ------------------------------------------------------------------ */

const eur = (n: number) =>
  n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const signo = (n: number) => (n >= 0 ? "+" : "");
const clase = (n: number) => (n >= 0 ? "positivo" : "negativo");

const fecha = (s: string) =>
  new Date(s).toLocaleDateString("es-ES", { day: "2-digit", month: "short" });

/* ------------------------------------------------------------------ */
/*  Curva de equity dibujada como SVG, sin librerías                   */
/* ------------------------------------------------------------------ */

function Curva({ puntos, color }: { puntos: { d: string; v: number }[]; color: string }) {
  if (puntos.length < 2) {
    return <p className="nota">Se dibujará cuando haya al menos dos días de historial.</p>;
  }

  const W = 800;
  const H = 200;
  const P = 8;
  const vals = puntos.map((p) => p.v);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const rango = max - min || 1;

  const x = (i: number) => (i / (puntos.length - 1)) * (W - P * 2) + P;
  const y = (v: number) => H - P - ((v - min) / rango) * (H - P * 2);

  const linea = puntos.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
  const area = `${linea} L${x(puntos.length - 1).toFixed(1)},${H} L${x(0).toFixed(1)},${H} Z`;

  return (
    <div className="grafico">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`Evolución del capital de ${eur(min)} a ${eur(max)}`}>
        <defs>
          <linearGradient id="relleno" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#relleno)" />
        <path d={linea} fill="none" stroke={color} strokeWidth="1.75"
              strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <div className="orden-fila" style={{ marginTop: 10 }}>
        <span className="dato nota">{fecha(puntos[0].d)} · {eur(puntos[0].v)}</span>
        <span className="dato nota">{fecha(puntos[puntos.length - 1].d)} · {eur(puntos[puntos.length - 1].v)}</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Página                                                             */
/* ------------------------------------------------------------------ */

export default function Pagina() {
  const { regimen, senales, cartera, metricas } = r;

  return (
    <main className="envoltura">

      {/* ---------- Cabecera ---------- */}
      <header className="cabecera">
        <div className="marca">
          <h1 className="titulo">Señales swing</h1>
          <span className="epigrafe">{r.universo} valores · S&amp;P 500 + Nasdaq 100</span>
        </div>

        <div className="estado">
          <span className={`punto ${regimen.alcista ? "punto--activo" : "punto--parado"}`} />
          <span>
            {regimen.alcista
              ? "Mercado alcista — el sistema puede abrir posiciones"
              : "Mercado bajista — el sistema no abre posiciones nuevas"}
          </span>
        </div>

        <p className="nota" style={{ marginTop: 12 }}>
          SPY en <span className="dato">{eur(regimen.spy)}</span>, su media de 200 sesiones en{" "}
          <span className="dato">{eur(regimen.sma200)}</span>{" "}
          (<span className={`dato ${clase(regimen.distancia_pct)}`}>
            {signo(regimen.distancia_pct)}{regimen.distancia_pct}%
          </span>). Datos del {r.fecha_datos}.
        </p>

        {r.es_demo && (
          <div className="aviso">
            <strong>Datos de ejemplo.</strong> Estas cifras son inventadas y sirven solo para
            comprobar que la página funciona. Lanza el flujo <em>Señales diarias</em> desde la
            pestaña Actions de GitHub para sustituirlas por datos reales de mercado.
          </div>
        )}
      </header>

      {/* ---------- Órdenes de mañana ---------- */}
      <section className="seccion">
        <div className="seccion-cabecera">
          <span className="epigrafe">Paso 1</span>
          <h2 className="seccion-titulo">Órdenes para mañana en la apertura</h2>
          <p className="nota">
            Cifras listas para copiar en el bróker. El stop se introduce en la misma orden.
          </p>
        </div>

        {senales.length === 0 ? (
          <div className="vacio">
            <p>Hoy no hay ninguna orden.</p>
            <p>
              {regimen.alcista
                ? "Ningún valor cumple las condiciones de entrada. No operar también es una decisión del sistema."
                : "El filtro de régimen está activo: mientras el SPY siga por debajo de su media de 200 sesiones, no se abren posiciones."}
            </p>
          </div>
        ) : (
          senales.map((s) => (
            <article className="orden" key={s.ticker}>
              <div className="orden-fila">
                <div>
                  <span className="orden-ticker">{s.ticker}</span>
                  <span className="orden-accion">COMPRAR</span>
                </div>
                <span className="orden-importe">{eur(s.importe)} $</span>
              </div>

              <hr className="orden-separador" />

              <div className="orden-campos">
                <div>
                  <span className="campo-etiqueta">Acciones</span>
                  <span className="campo-valor">{s.acciones}</span>
                </div>
                <div>
                  <span className="campo-etiqueta">Referencia</span>
                  <span className="campo-valor">{eur(s.precio_ref)}</span>
                </div>
                <div>
                  <span className="campo-etiqueta">Stop</span>
                  <span className="campo-valor negativo">{eur(s.stop)}</span>
                </div>
                <div>
                  <span className="campo-etiqueta">Riesgo</span>
                  <span className="campo-valor destacado">{eur(s.riesgo_eur)} $</span>
                </div>
                <div>
                  <span className="campo-etiqueta">RSI(4)</span>
                  <span className="campo-valor">{s.rsi}</span>
                </div>
                <div>
                  <span className="campo-etiqueta">Fuerza 6m</span>
                  <span className={`campo-valor ${clase(s.roc)}`}>
                    {signo(s.roc)}{s.roc}%
                  </span>
                </div>
              </div>
            </article>
          ))
        )}
      </section>

      {/* ---------- Cartera fantasma ---------- */}
      <section className="seccion">
        <div className="seccion-cabecera">
          <span className="epigrafe">Paso 2</span>
          <h2 className="seccion-titulo">Cartera fantasma</h2>
          <p className="nota">
            Dinero ficticio, precios reales. Ejecuta las mismas reglas sin arriesgar nada.
          </p>
        </div>

        <div className="rejilla">
          <div className="celda">
            <span className="campo-etiqueta">Capital</span>
            <div className="celda-valor">{eur(cartera.equity)}</div>
          </div>
          <div className="celda">
            <span className="campo-etiqueta">Resultado</span>
            <div className={`celda-valor ${clase(cartera.retorno_pct)}`}>
              {signo(cartera.retorno_pct)}{cartera.retorno_pct}%
            </div>
          </div>
          <div className="celda">
            <span className="campo-etiqueta">Liquidez</span>
            <div className="celda-valor">{eur(cartera.cash)}</div>
          </div>
          <div className="celda">
            <span className="campo-etiqueta">Abiertas</span>
            <div className="celda-valor">{cartera.posiciones.length} / 5</div>
          </div>
        </div>

        {cartera.posiciones.length > 0 && (
          <div className="desplazable" style={{ marginTop: 28 }}>
            <table className="tabla">
              <thead>
                <tr>
                  <th>Valor</th><th>Entrada</th><th>Actual</th>
                  <th>Stop</th><th>Result.</th><th>Días</th>
                </tr>
              </thead>
              <tbody>
                {cartera.posiciones.map((p) => (
                  <tr key={p.ticker}>
                    <td style={{ fontWeight: 600 }}>{p.ticker}</td>
                    <td>{eur(p.precio)}</td>
                    <td>{eur(p.precio_actual)}</td>
                    <td className="negativo">{eur(p.stop)}</td>
                    <td className={clase(p.pnl_pct)}>{signo(p.pnl_pct)}{p.pnl_pct}%</td>
                    <td>{p.dias}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {cartera.curva.length >= 2 && (
          <div style={{ marginTop: 28 }}>
            <Curva puntos={cartera.curva}
                   color={cartera.retorno_pct >= 0 ? "#5fd3a6" : "#e8705f"} />
          </div>
        )}

        {cartera.cerradas.length > 0 && (
          <div style={{ marginTop: 36 }}>
            <span className="epigrafe">Últimas operaciones cerradas</span>
            <div className="desplazable" style={{ marginTop: 12 }}>
              <table className="tabla">
                <thead>
                  <tr>
                    <th>Valor</th><th>Entrada</th><th>Salida</th>
                    <th>Result.</th><th>Días</th><th>Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {cartera.cerradas.map((c, i) => (
                    <tr key={`${c.ticker}-${i}`}>
                      <td style={{ fontWeight: 600 }}>{c.ticker}</td>
                      <td>{fecha(c.entrada_fecha)}</td>
                      <td>{fecha(c.salida_fecha)}</td>
                      <td className={clase(c.pnl_pct)}>
                        {signo(c.pnl_pct)}{c.pnl_pct}%
                      </td>
                      <td>{c.dias}</td>
                      <td style={{ color: "var(--apagado)" }}>{c.motivo}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* ---------- Salud del sistema ---------- */}
      <section className="seccion">
        <div className="seccion-cabecera">
          <span className="epigrafe">Paso 3</span>
          <h2 className="seccion-titulo">Salud del sistema</h2>
          <p className="nota">
            Resultado de aplicar estas reglas al histórico desde 2015. Si el factor de beneficio
            baja de 1,3 o la caída máxima supera el 20%, toca revisar las reglas.
          </p>
        </div>

        <div className="rejilla">
          {["CAGR", "Max Drawdown", "Profit factor", "Win rate",
            "Ratio R medio", "Nº operaciones", "Sharpe", "Días medios"].map((k) => (
            <div className="celda" key={k}>
              <span className="campo-etiqueta">{k}</span>
              <div className="celda-valor">{String(metricas[k] ?? "—")}</div>
            </div>
          ))}
        </div>

        <p className="nota" style={{ marginTop: 16 }}>
          Comprar y mantener el SPY en el mismo periodo:{" "}
          <span className={`dato ${clase(r.buy_and_hold_spy)}`}>
            {signo(r.buy_and_hold_spy)}{r.buy_and_hold_spy}%
          </span>. Si el sistema no bate esta cifra ajustada por riesgo, el índice es mejor opción.
        </p>

        {r.curva_backtest.length >= 2 && (
          <div style={{ marginTop: 24 }}>
            <Curva puntos={r.curva_backtest} color="#f2a93b" />
          </div>
        )}
      </section>

      {/* ---------- Pie ---------- */}
      <footer className="pie">
        <p>
          Actualizado el {new Date(r.generado).toLocaleString("es-ES")}. El motor se ejecuta
          de lunes a viernes a las 22:30, tras el cierre del mercado americano.
        </p>
        <p style={{ marginTop: 10 }}>
          Herramienta de uso personal. No es asesoramiento financiero. Los resultados históricos
          no anticipan los futuros y operar en bolsa puede acarrear la pérdida del capital.
        </p>
      </footer>
    </main>
  );
}
