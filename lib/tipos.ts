export type Senal = {
  ticker: string;
  precio_ref: number;
  stop: number;
  acciones: number;
  importe: number;
  riesgo_eur: number;
  rsi: number;
  atr: number;
  roc: number;
};

export type Posicion = {
  ticker: string;
  fecha: string;
  precio: number;
  precio_actual: number;
  acciones: number;
  stop: number;
  pnl_pct: number;
  dias: number;
};

export type Cerrada = {
  ticker: string;
  acciones?: number;
  entrada_fecha: string;
  salida_fecha: string;
  entrada: number;
  salida: number;
  pnl: number;
  pnl_pct: number;
  dias: number;
  motivo: string;
};

export type Cartera = {
  equity: number;
  cash: number;
  capital_inicial: number;
  retorno_pct: number;
  posiciones: Posicion[];
  cerradas: Cerrada[];
  curva: { d: string; v: number }[];
  ultimo_rebalanceo?: string | null;
};

export type Resultados = {
  generado: string;
  fecha_datos: string;
  es_demo: boolean;
  regimen: { alcista: boolean; spy: number; sma200: number; distancia_pct: number };
  senales: Senal[];
  cartera: Cartera;
  cartera_momentum?: Cartera;
  top_momentum?: string[];
  metricas: Record<string, string | number>;
  buy_and_hold_spy: number;
  curva_backtest: { d: string; v: number }[];
  universo: number;
};
