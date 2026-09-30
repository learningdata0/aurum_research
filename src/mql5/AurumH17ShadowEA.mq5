//+------------------------------------------------------------------+
//|                                           AurumH17ShadowEA.mq5   |
//|                                  Copyright 2026, AURUM Research |
//|        AURUM v0.8: Autonomous Virtual Forward Shadow Engine      |
//|               Strategy H17: London Session Sweep-Reclaim         |
//+------------------------------------------------------------------+
#property copyright   "AURUM Research"
#property link        "https://github.com/aurum-research"
#property version     "1.00"
#property description "AURUM v0.8 Virtual Paper Trading EA for UT100Roll / US100."
#property description "Trades London Session liquidity sweeps with median expansion filter (>=140pts)."

//--- Inputs
input group "=== Trading Mode ==="
input bool   InpVirtualMode       = true;     // Virtual Paper Mode (No real financial risk)
input double InpInitialBalance    = 10000.0;  // Virtual Starting Balance ($)
input double InpRiskPercent       = 0.25;     // Risk per trade (0.25% = 1R)
input int    InpMagicNumber       = 77717;    // Magic number for demo/live orders

input group "=== Strategy Parameters (H17 Frozen) ==="
input double InpMinLondonRange    = 140.0;    // Minimum London Session Range in points
input int    InpATRPeriod         = 14;       // ATR Period for Stop Loss padding
input double InpSweepBufferATR    = 0.05;     // Min penetration beyond London level (ATR multiple)
input int    InpMaxHoldBars       = 120;      // Max hold duration in M1 bars

//--- Session Hour Constants (Broker Time: UTC+3 EEST / UTC+2 EET)
// Broker is aligned with US-DST (16:30 Broker = 09:30 AM New York)
const int LONDON_START_HOUR = 10; // 03:00 NY
const int LONDON_END_HOUR   = 16; // 09:00 NY
const int NY_OPEN_HOUR      = 16;
const int NY_OPEN_MIN       = 30; // 09:30 NY Cash Open
const int NY_CLOSE_HOUR     = 22;
const int NY_CLOSE_MIN      = 30; // 15:30 NY Cash Session

//--- Virtual Trade State
struct VirtualTrade
{
   int      ticket;
   datetime entry_time;
   string   direction;  // "BUY" or "SELL"
   double   entry_price;
   double   sl;
   double   tp;
   double   units;
   double   risk_cash;
   int      entry_bar;
   bool     is_open;
};

VirtualTrade g_trade;
double       g_virtual_balance;
int          g_ticket_counter;
datetime     g_last_bar_time;

// Today's HTF Levels
double   g_london_high;
double   g_london_low;
double   g_london_mid;
double   g_london_range;
bool     g_london_qualified;
datetime g_current_day;

int      g_atr_handle;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   g_virtual_balance  = InpInitialBalance;
   g_ticket_counter   = 1000;
   g_trade.is_open    = false;
   g_last_bar_time    = 0;
   g_current_day      = 0;

   g_london_high      = 0.0;
   g_london_low       = 0.0;
   g_london_mid       = 0.0;
   g_london_range     = 0.0;
   g_london_qualified = false;

   // Create ATR indicator handle
   g_atr_handle = iATR(_Symbol, PERIOD_M1, InpATRPeriod);
   if(g_atr_handle == INVALID_HANDLE)
   {
      Print("[ERROR] Failed to create ATR handle.");
      return INIT_FAILED;
   }

   // Initialize log file
   InitCsvLog();

   // Draw initial dashboard
   UpdateDashboard("INITIALIZED — WAITING FOR DATA");

   PrintFormat("[AURUM H17] Virtual Shadow Engine initialized on %s (VirtualMode=%s, Risk=%.2f%%, MinLondonRange=%.1f pts)",
               _Symbol, InpVirtualMode ? "TRUE" : "FALSE", InpRiskPercent, InpMinLondonRange);

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(g_atr_handle);
   Comment("");
   // Clean visual lines
   ObjectDelete(0, "AURUM_LH");
   ObjectDelete(0, "AURUM_LL");
   ObjectDelete(0, "AURUM_MID");
   ObjectDelete(0, "AURUM_SL");
   ObjectDelete(0, "AURUM_TP");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // 1. Check open virtual trade for TP/SL touch on every tick
   if(g_trade.is_open)
   {
      MqlTick tick;
      if(SymbolInfoTick(_Symbol, tick))
      {
         CheckVirtualTradeExit(tick);
      }
   }

   // 2. Only evaluate signals on completed new M1 bar
   datetime current_bar_time = iTime(_Symbol, PERIOD_M1, 0);
   if(current_bar_time == g_last_bar_time)
      return;
   g_last_bar_time = current_bar_time;

   // 3. Update Daily Context & London Levels
   MqlDateTime dt;
   TimeCurrent(dt);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d", dt.year, dt.mon, dt.day));

   if(today != g_current_day)
   {
      g_current_day = today;
      CalculateLondonLevels(today);
   }

   // 4. Update London Levels if in London session
   if(dt.hour >= LONDON_START_HOUR && dt.hour < LONDON_END_HOUR)
   {
      CalculateLondonLevels(today);
   }

   // 5. Check if within NY Cash Session (16:30 to 22:30 broker time)
   int current_min_of_day = dt.hour * 60 + dt.min;
   int ny_open_min        = NY_OPEN_HOUR * 60 + NY_OPEN_MIN;
   int ny_close_min       = NY_CLOSE_HOUR * 60 + NY_CLOSE_MIN;

   bool in_ny_session = (current_min_of_day >= ny_open_min && current_min_of_day < ny_close_min);

   // 6. Signal Evaluation
   if(in_ny_session && g_london_qualified && !g_trade.is_open)
   {
      EvaluateH17Signal();
   }

   // 7. Update on-chart status dashboard
   string state_str = in_ny_session ? (g_london_qualified ? "ACTIVE (MONITORING SWEEPS)" : "SKIPPED (RANGE < 140pts)") : "OUTSIDE NY SESSION";
   if(g_trade.is_open)
      state_str = StringFormat("IN TRADE [%s] Ticket #%d", g_trade.direction, g_trade.ticket);

   UpdateDashboard(state_str);
}

//+------------------------------------------------------------------+
//| Calculate London Session (10:00 to 16:00 broker time) High & Low |
//+------------------------------------------------------------------+
void CalculateLondonLevels(datetime day_start)
{
   datetime lon_start = day_start + LONDON_START_HOUR * 3600;
   datetime lon_end   = day_start + LONDON_END_HOUR * 3600;

   int start_idx = iBarShift(_Symbol, PERIOD_M1, lon_start);
   int end_idx   = iBarShift(_Symbol, PERIOD_M1, lon_end);

   if(start_idx < 0 || end_idx < 0 || start_idx <= end_idx)
      return;

   int count = start_idx - end_idx + 1;
   int highest_idx = iHighest(_Symbol, PERIOD_M1, MODE_HIGH, count, end_idx);
   int lowest_idx  = iLowest(_Symbol, PERIOD_M1, MODE_LOW, count, end_idx);

   if(highest_idx >= 0 && lowest_idx >= 0)
   {
      g_london_high      = iHigh(_Symbol, PERIOD_M1, highest_idx);
      g_london_low       = iLow(_Symbol, PERIOD_M1, lowest_idx);
      g_london_mid       = (g_london_high + g_london_low) / 2.0;
      g_london_range     = g_london_high - g_london_low;
      g_london_qualified = (g_london_range >= InpMinLondonRange);

      // Draw horizontal reference lines on chart
      DrawHLine("AURUM_LH", g_london_high, clrDodgerBlue, "London High");
      DrawHLine("AURUM_LL", g_london_low, clrDodgerBlue, "London Low");
      DrawHLine("AURUM_MID", g_london_mid, clrDarkGray, "London Midpoint", STYLE_DOT);
   }
}

//+------------------------------------------------------------------+
//| Evaluate H17 Sweep-Reclaim Signal on closed bar 1                |
//+------------------------------------------------------------------+
void EvaluateH17Signal()
{
   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(g_atr_handle, 0, 1, 1, atr) <= 0) return;
   double current_atr = atr[0];

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, PERIOD_M1, 1, 2, rates) < 2) return;

   MqlRates r = rates[0]; // Bar 1 (most recently closed bar)
   double c_range = MathMax(r.high - r.low, 0.01);
   double upper_wick = r.high - MathMax(r.open, r.close);
   double lower_wick = MathMin(r.open, r.close) - r.low;
   double sweep_buffer = MathMax(InpSweepBufferATR * current_atr, 1.0);

   // 1. Bearish Sweep of London High
   bool swept_h = (r.high >= g_london_high + sweep_buffer);
   bool reclaimed_h = (r.close < g_london_high && r.close > g_london_low);
   bool bearish_confirm = (r.close < r.open || (upper_wick >= 0.25 * c_range));

   if(swept_h && reclaimed_h && bearish_confirm)
   {
      double entry = r.close;
      double sl    = r.high + 0.10 * current_atr;
      double tp    = g_london_mid;
      double risk  = sl - entry;

      if(risk > 0 && tp < entry && (entry - tp) / risk >= 1.25)
      {
         ExecuteOrder("SELL", entry, sl, tp, risk);
         return;
      }
   }

   // 2. Bullish Sweep of London Low
   bool swept_l = (r.low <= g_london_low - sweep_buffer);
   bool reclaimed_l = (r.close > g_london_low && r.close < g_london_high);
   bool bullish_confirm = (r.close > r.open || (lower_wick >= 0.25 * c_range));

   if(swept_l && reclaimed_l && bullish_confirm)
   {
      double entry = r.close;
      double sl    = r.low - 0.10 * current_atr;
      double tp    = g_london_mid;
      double risk  = entry - sl;

      if(risk > 0 && tp > entry && (tp - entry) / risk >= 1.25)
      {
         ExecuteOrder("BUY", entry, sl, tp, risk);
         return;
      }
   }
}

//+------------------------------------------------------------------+
//| Execute Virtual or Demo Order                                    |
//+------------------------------------------------------------------+
void ExecuteOrder(string dir, double entry, double sl, double tp, double risk_pts)
{
   double risk_cash = g_virtual_balance * (InpRiskPercent / 100.0);
   double units     = risk_cash / risk_pts;

   g_trade.ticket      = g_ticket_counter++;
   g_trade.entry_time  = TimeCurrent();
   g_trade.direction   = dir;
   g_trade.entry_price = entry;
   g_trade.sl          = sl;
   g_trade.tp          = tp;
   g_trade.units       = units;
   g_trade.risk_cash   = risk_cash;
   g_trade.entry_bar   = 0;
   g_trade.is_open     = true;

   // Visual lines on chart
   DrawHLine("AURUM_SL", sl, clrRed, "Stop Loss", STYLE_DASH);
   DrawHLine("AURUM_TP", tp, clrGreen, "Take Profit (Midpoint)", STYLE_DASH);

   string alert_msg = StringFormat("[AURUM H17] %s ORDER #%d | Entry: %.2f | SL: %.2f | TP: %.2f | Risk: $%.2f (1R)",
                                   dir, g_trade.ticket, entry, sl, tp, risk_cash);
   Print(alert_msg);
   Alert(alert_msg);

   // Log to CSV
   LogTradeToCsv(g_trade, "OPEN", 0.0, 0.0, "");
}

//+------------------------------------------------------------------+
//| Check Virtual Trade Exit on Tick                                 |
//+------------------------------------------------------------------+
void CheckVirtualTradeExit(const MqlTick &tick)
{
   bool hit_tp = false;
   bool hit_sl = false;
   double exit_price = 0.0;
   string reason = "";

   if(g_trade.direction == "BUY")
   {
      if(tick.bid >= g_trade.tp) { hit_tp = true; exit_price = g_trade.tp; reason = "TP"; }
      else if(tick.bid <= g_trade.sl) { hit_sl = true; exit_price = g_trade.sl; reason = "SL"; }
   }
   else // SELL
   {
      if(tick.ask <= g_trade.tp) { hit_tp = true; exit_price = g_trade.tp; reason = "TP"; }
      else if(tick.ask >= g_trade.sl) { hit_sl = true; exit_price = g_trade.sl; reason = "SL"; }
   }

   // Time Exit (120 bars)
   if(!hit_tp && !hit_sl)
   {
      int bars_held = iBarShift(_Symbol, PERIOD_M1, g_trade.entry_time);
      if(bars_held >= InpMaxHoldBars)
      {
         exit_price = (g_trade.direction == "BUY") ? tick.bid : tick.ask;
         reason = "TIME";
      }
   }

   if(exit_price > 0.0)
   {
      double pts = (g_trade.direction == "BUY") ? (exit_price - g_trade.entry_price) : (g_trade.entry_price - exit_price);
      double pnl = pts * g_trade.units;
      double r_mult = (g_trade.risk_cash > 0) ? (pnl / g_trade.risk_cash) : 0.0;

      g_virtual_balance += pnl;
      g_trade.is_open = false;

      // Clean lines
      ObjectDelete(0, "AURUM_SL");
      ObjectDelete(0, "AURUM_TP");

      string close_msg = StringFormat("[AURUM H17] CLOSED #%d by %s | PnL: $%.2f (%+.2fR) | Balance: $%.2f",
                                      g_trade.ticket, reason, pnl, r_mult, g_virtual_balance);
      Print(close_msg);
      Alert(close_msg);

      LogTradeToCsv(g_trade, "CLOSED", pnl, r_mult, reason);
   }
}

//+------------------------------------------------------------------+
//| Chart Dashboard Display                                          |
//+------------------------------------------------------------------+
void UpdateDashboard(string status_text)
{
   string q_text = g_london_qualified ? "QUALIFIED (>= 140 pts)" : "UNQUALIFIED (< 140 pts)";
   string dash = StringFormat(
      "====================================================\n"
      " AURUM v0.8 SHADOW TRADING ENGINE [H17]\n"
      " Symbol: %s | Mode: %s\n"
      "----------------------------------------------------\n"
      " London High: %.2f | London Low: %.2f\n"
      " London Range: %.2f pts [%s]\n"
      " London Midpoint Target: %.2f\n"
      "----------------------------------------------------\n"
      " Engine Status: %s\n"
      " Virtual Account Balance: $%.2f\n"
      "====================================================",
      _Symbol, InpVirtualMode ? "VIRTUAL PAPER (ZERO RISK)" : "DEMO BROKER",
      g_london_high, g_london_low, g_london_range, q_text, g_london_mid,
      status_text, g_virtual_balance
   );
   Comment(dash);
}

//+------------------------------------------------------------------+
//| Draw Horizontal Line Helper                                      |
//+------------------------------------------------------------------+
void DrawHLine(string name, double price, color clr, string desc, ENUM_LINE_STYLE style=STYLE_DASH)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   }
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetString(0, name, OBJPROP_TEXT, desc);
}

//+------------------------------------------------------------------+
//| CSV Logging in MQL5/Files/                                       |
//+------------------------------------------------------------------+
void InitCsvLog()
{
   int file = FileOpen("aurum_shadow_trades.csv", FILE_READ | FILE_WRITE | FILE_CSV);
   if(file != INVALID_HANDLE)
   {
      if(FileSize(file) == 0)
      {
         FileWrite(file, "ticket", "time", "action", "symbol", "direction", "entry", "sl", "tp", "pnl", "r_mult", "reason", "balance");
      }
      FileClose(file);
   }
}

void LogTradeToCsv(const VirtualTrade &t, string action, double pnl, double r_mult, string reason)
{
   int file = FileOpen("aurum_shadow_trades.csv", FILE_READ | FILE_WRITE | FILE_CSV);
   if(file != INVALID_HANDLE)
   {
      FileSeek(file, 0, SEEK_END);
      FileWrite(file, t.ticket, TimeToString(TimeCurrent()), action, _Symbol, t.direction,
                DoubleToString(t.entry_price, 2), DoubleToString(t.sl, 2), DoubleToString(t.tp, 2),
                DoubleToString(pnl, 2), DoubleToString(r_mult, 2), reason, DoubleToString(g_virtual_balance, 2));
      FileClose(file);
   }
}
