//+------------------------------------------------------------------+
//|                                       AurumGoldH17ShadowEA.mq5   |
//|                                  Copyright 2026, AURUM Research |
//|        AURUM v0.9: Autonomous Virtual Forward Shadow Engine      |
//|               Strategy: Gold London Session Sweep-Reclaim        |
//|        Equipped with Hybrid TP1 (50%), Breakeven & Trailing Stop |
//+------------------------------------------------------------------+
#property copyright   "AURUM Research"
#property link        "https://github.com/aurum-research"
#property version     "1.10"
#property description "AURUM v0.9 Virtual Paper Trading EA for XAUUSD (Gold)."
#property description "Trades Gold London Session sweeps with TP1 (50% partial), Breakeven lock & Multi-Stage Trailing."

//--- Inputs
input group "=== Trading Mode ==="
input bool   InpVirtualMode       = true;     // Virtual Paper Mode (No real financial risk)
input double InpInitialBalance    = 10000.0;  // Virtual Starting Balance ($)
input double InpRiskPercent       = 0.25;     // Risk per trade (0.25% = 1R)
input int    InpMagicNumber       = 77718;    // Magic number for demo/live orders

input group "=== Strategy Parameters (Gold H17 Frozen) ==="
input double InpMinLondonRange    = 55.0;     // Minimum London Session Range in points ($55/oz)
input int    InpATRPeriod         = 14;       // ATR Period for Stop Loss padding
input double InpSweepBufferATR    = 0.05;     // Min penetration beyond London level (ATR multiple)
input int    InpMaxHoldBars       = 120;      // Max hold duration in M1 bars

input group "=== Dynamic Risk & Trade Management ==="
input bool   InpEnableHybridTP1   = true;     // Enable 50% TP1 partial close
input double InpTP1Points         = 4.0;      // TP1 trigger distance in points ($4/oz)
input bool   InpEnableBreakeven   = true;     // Move SL to Breakeven after TP1
input bool   InpEnableTrailing    = true;     // Enable multi-stage trailing stop
input double InpTrailStep1Pts     = 7.0;      // Points in profit to trigger Trail Step 1
input double InpTrailLock1Pts     = 3.0;      // Profit points locked at Trail Step 1
input double InpTrailStep2Pts     = 12.0;     // Points in profit to trigger Trail Step 2
input double InpTrailLock2Pts     = 6.0;      // Profit points locked at Trail Step 2

//--- Pre-Entry Institutional Safeguards (v1.2)
input int    InpOpeningBufferMin  = 15;       // Opening bell buffer in minutes (16:30 - 16:45)
input double InpMinSLPoints       = 3.5;      // Minimum Stop Loss floor in points ($3.5/oz)
input int    InpLossCooldownMin   = 15;       // Cooldown minutes after a loss before re-entering

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
   bool     tp1_closed;      // true if 50% closed at TP1
   double   tp1_price;       // price of TP1
   double   tp1_cash;        // profit banked from TP1
   bool     be_moved;        // true if SL moved to Breakeven
};

VirtualTrade g_trade;
double       g_virtual_balance;
int          g_ticket_counter;
datetime     g_last_bar_time;
datetime     g_last_loss_time;

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
   g_last_loss_time   = 0;
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

   PrintFormat("[AURUM GOLD H17 v1.2] Virtual Shadow Engine initialized on %s (VirtualMode=%s, TP1=%.1f pts, MinSL=%.1f pts, OpenBuffer=%d min, LossCooldown=%d min)",
               _Symbol, InpVirtualMode ? "TRUE" : "FALSE", InpTP1Points, InpMinSLPoints, InpOpeningBufferMin, InpLossCooldownMin);

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
   ObjectDelete(0, "AURUM_GOLD_LH");
   ObjectDelete(0, "AURUM_GOLD_LL");
   ObjectDelete(0, "AURUM_GOLD_MID");
   ObjectDelete(0, "AURUM_GOLD_SL");
   ObjectDelete(0, "AURUM_GOLD_TP");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // 1. Check open virtual trade for TP/SL touch and trailing stop on every tick
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

   // Opening Bell Buffer: skip first InpOpeningBufferMin minutes (e.g. 16:30 - 16:45)
   int active_open_min    = ny_open_min + InpOpeningBufferMin;
   bool in_ny_session     = (current_min_of_day >= active_open_min && current_min_of_day < ny_close_min);
   bool in_opening_buffer = (current_min_of_day >= ny_open_min && current_min_of_day < active_open_min);

   // Loss Cooldown: wait InpLossCooldownMin minutes after any SL
   bool in_loss_cooldown  = (TimeCurrent() < g_last_loss_time + InpLossCooldownMin * 60);

   // 6. Signal Evaluation
   if(in_ny_session && g_london_qualified && !g_trade.is_open && !in_loss_cooldown)
   {
      EvaluateGoldH17Signal();
   }

   // 7. Update on-chart status dashboard
   string state_str = in_ny_session ? (in_loss_cooldown ? "LOSS COOLDOWN ACTIVE" : (g_london_qualified ? "ACTIVE (MONITORING SWEEPS)" : "SKIPPED (RANGE < 55pts)")) : (in_opening_buffer ? "OPENING BELL BUFFER (15m)" : "OUTSIDE NY SESSION");
   if(g_trade.is_open)
   {
      state_str = StringFormat("IN TRADE #%d (%s) | PnL: %s",
                               g_trade.ticket, g_trade.direction,
                               g_trade.tp1_closed ? "TP1 SECURED + RUNNING" : "OPEN");
   }
   UpdateDashboard(state_str);
}

//+------------------------------------------------------------------+
//| Calculate London High, Low, Midpoint for today                   |
//+------------------------------------------------------------------+
void CalculateLondonLevels(datetime day)
{
   datetime london_start = day + LONDON_START_HOUR * 3600;
   datetime london_end   = day + LONDON_END_HOUR   * 3600;

   int start_bar = iBarShift(_Symbol, PERIOD_M1, london_start);
   int end_bar   = iBarShift(_Symbol, PERIOD_M1, london_end);

   if(start_bar < 0 || end_bar < 0 || start_bar <= end_bar)
      return;

   int count = start_bar - end_bar + 1;
   double highs[], lows[];
   ArraySetAsSeries(highs, true);
   ArraySetAsSeries(lows, true);

   if(CopyHigh(_Symbol, PERIOD_M1, end_bar, count, highs) < count) return;
   if(CopyLow(_Symbol, PERIOD_M1, end_bar, count, lows) < count) return;

   g_london_high  = highs[ArrayMaximum(highs)];
   g_london_low   = lows[ArrayMinimum(lows)];
   g_london_range = g_london_high - g_london_low;
   g_london_mid   = (g_london_high + g_london_low) / 2.0;

   g_london_qualified = (g_london_range >= InpMinLondonRange);

   // Draw visual levels
   DrawHLine("AURUM_GOLD_LH",  g_london_high, clrRed,        StringFormat("Gold London High (%.2f)", g_london_high));
   DrawHLine("AURUM_GOLD_LL",  g_london_low,  clrDodgerBlue, StringFormat("Gold London Low (%.2f)", g_london_low));
   DrawHLine("AURUM_GOLD_MID", g_london_mid,  clrGold,       StringFormat("Gold London Midpoint (%.2f)", g_london_mid));
}

//+------------------------------------------------------------------+
//| Evaluate Gold Sweep-Reclaim Setup on Bar Close                   |
//+------------------------------------------------------------------+
void EvaluateGoldH17Signal()
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, PERIOD_M1, 1, 2, rates) < 2)
      return;

   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(g_atr_handle, 0, 1, 1, atr) < 1)
      return;

   double current_atr  = atr[0];
   double sweep_buffer = InpSweepBufferATR * current_atr;

   MqlRates r = rates[0]; // just completed bar
   double c_range = r.high - r.low;
   if(c_range <= 0) return;

   double upper_wick = r.high - MathMax(r.open, r.close);
   double lower_wick = MathMin(r.open, r.close) - r.low;

   // 1. Bearish Sweep of London High
   bool swept_h = (r.high >= g_london_high + sweep_buffer);
   bool reclaimed_h = (r.close < g_london_high && r.close > g_london_low);
   bool bearish_confirm = (r.close < r.open || (upper_wick >= 0.25 * c_range));

   if(swept_h && reclaimed_h && bearish_confirm)
   {
      double entry = r.close;
      double sl    = r.high + 0.10 * current_atr;
      if(sl - entry < InpMinSLPoints)
         sl = entry + InpMinSLPoints;

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
      if(entry - sl < InpMinSLPoints)
         sl = entry - InpMinSLPoints;

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
   g_trade.tp1_closed  = false;
   g_trade.tp1_price   = 0.0;
   g_trade.tp1_cash    = 0.0;
   g_trade.be_moved    = false;

   // Visual lines on chart
   DrawHLine("AURUM_GOLD_SL", sl, clrRed, "Stop Loss", STYLE_DASH);
   DrawHLine("AURUM_GOLD_TP", tp, clrGreen, "Take Profit (Midpoint)", STYLE_DASH);

   string alert_msg = StringFormat("[AURUM GOLD H17 v1.1] %s ORDER #%d | Entry: %.2f | SL: %.2f | TP: %.2f | Risk: $%.2f (1R)",
                                   dir, g_trade.ticket, entry, sl, tp, risk_cash);
   Print(alert_msg);
   Alert(alert_msg);

   // Log to CSV
   LogTradeToCsv(g_trade, "OPEN", 0.0, 0.0, "");
}

//+------------------------------------------------------------------+
//| Check Virtual Trade Exit on Tick with Trailing & TP1             |
//+------------------------------------------------------------------+
void CheckVirtualTradeExit(const MqlTick &tick)
{
   double current_price = (g_trade.direction == "BUY") ? tick.bid : tick.ask;
   double favorable_pts = (g_trade.direction == "BUY") ? (current_price - g_trade.entry_price) : (g_trade.entry_price - current_price);

   // 1. Check Partial TP1
   if(InpEnableHybridTP1 && !g_trade.tp1_closed)
   {
      if(favorable_pts >= InpTP1Points)
      {
         g_trade.tp1_closed = true;
         g_trade.tp1_price  = current_price;
         g_trade.tp1_cash   = (InpTP1Points * 0.5 * g_trade.units);
         
         // Move Stop Loss to Breakeven
         if(InpEnableBreakeven)
         {
            g_trade.sl = g_trade.entry_price;
            g_trade.be_moved = true;
            DrawHLine("AURUM_GOLD_SL", g_trade.sl, clrGold, "Stop Loss (BREAKEVEN)", STYLE_DASH);
         }
         
         string tp1_msg = StringFormat("[AURUM GOLD H17] TP1 REACHED #%d at %.2f (+%.1f pts) | 50%% Banked ($%.2f) | SL Moved to Breakeven",
                                       g_trade.ticket, current_price, InpTP1Points, g_trade.tp1_cash);
         Print(tp1_msg);
      }
   }

   // 2. Dynamic Multi-Stage Trailing Stop (active after TP1 or if BE locked)
   if(InpEnableTrailing && g_trade.tp1_closed)
   {
      // Stage 2: Lock profit at Step 2
      if(favorable_pts >= InpTrailStep2Pts)
      {
         double target_sl = (g_trade.direction == "BUY") ? (g_trade.entry_price + InpTrailLock2Pts) : (g_trade.entry_price - InpTrailLock2Pts);
         bool should_update = (g_trade.direction == "BUY") ? (target_sl > g_trade.sl) : (target_sl < g_trade.sl);
         if(should_update)
         {
            g_trade.sl = target_sl;
            DrawHLine("AURUM_GOLD_SL", g_trade.sl, clrDodgerBlue, "Stop Loss (TRAIL 2)", STYLE_DASH);
         }
      }
      // Stage 1: Lock profit at Step 1
      else if(favorable_pts >= InpTrailStep1Pts)
      {
         double target_sl = (g_trade.direction == "BUY") ? (g_trade.entry_price + InpTrailLock1Pts) : (g_trade.entry_price - InpTrailLock1Pts);
         bool should_update = (g_trade.direction == "BUY") ? (target_sl > g_trade.sl) : (target_sl < g_trade.sl);
         if(should_update)
         {
            g_trade.sl = target_sl;
            DrawHLine("AURUM_GOLD_SL", g_trade.sl, clrDodgerBlue, "Stop Loss (TRAIL 1)", STYLE_DASH);
         }
      }
   }

   // 3. Check SL Hit
   bool hit_sl = false;
   if(g_trade.direction == "BUY" && tick.bid <= g_trade.sl) hit_sl = true;
   else if(g_trade.direction == "SELL" && tick.ask >= g_trade.sl) hit_sl = true;

   // 4. Check Final TP Hit (Midpoint)
   bool hit_tp = false;
   if(g_trade.direction == "BUY" && tick.bid >= g_trade.tp) hit_tp = true;
   else if(g_trade.direction == "SELL" && tick.ask <= g_trade.tp) hit_tp = true;

   // 5. Time Exit (120 bars)
   bool hit_time = false;
   if(!hit_tp && !hit_sl)
   {
      int bars_held = iBarShift(_Symbol, PERIOD_M1, g_trade.entry_time);
      if(bars_held >= InpMaxHoldBars) hit_time = true;
   }

   if(hit_sl || hit_tp || hit_time)
   {
      double exit_price = current_price;
      string reason = hit_tp ? "TP_FULL" : (hit_sl ? (g_trade.be_moved ? "BE_STOP" : "SL") : "TIME");
      
      double p2_pts = (g_trade.direction == "BUY") ? (exit_price - g_trade.entry_price) : (g_trade.entry_price - exit_price);
      double p2_units = g_trade.tp1_closed ? (0.5 * g_trade.units) : g_trade.units;
      double p2_cash = p2_pts * p2_units;
      
      double total_pnl = g_trade.tp1_cash + p2_cash;
      double r_mult = (g_trade.risk_cash > 0) ? (total_pnl / g_trade.risk_cash) : 0.0;
      
      g_virtual_balance += total_pnl;
      g_trade.is_open = false;

      if(reason == "SL")
      {
         g_last_loss_time = TimeCurrent();
      }
      
      ObjectDelete(0, "AURUM_GOLD_SL");
      ObjectDelete(0, "AURUM_GOLD_TP");
      
      string close_msg = StringFormat("[AURUM GOLD H17 v1.2] CLOSED #%d by %s | Net PnL: $%.2f (%+.2fR) | Balance: $%.2f",
                                      g_trade.ticket, reason, total_pnl, r_mult, g_virtual_balance);
      Print(close_msg);
      Alert(close_msg);
      
      LogTradeToCsv(g_trade, "CLOSED", total_pnl, r_mult, reason);
   }
}

//+------------------------------------------------------------------+
//| Chart Dashboard Display                                          |
//+------------------------------------------------------------------+
void UpdateDashboard(string status_text)
{
   string q_text = g_london_qualified ? "QUALIFIED (>= 55.0 pts)" : "UNQUALIFIED (< 55.0 pts)";
   string dash = StringFormat(
      "=== AURUM v0.9 DUAL-ASSET SHADOW DESK ===\n"
      "Symbol: %s | Mode: %s | Hybrid TP1: %s (%.1f pts)\n"
      "Virtual Balance: $%.2f\n"
      "London High: %.2f | Low: %.2f | Mid: %.2f\n"
      "London Range: %.2f pts [%s]\n"
      "Engine Status: %s\n"
      "Trailing Mode: %s (Step1: +%.0f pts | Step2: +%.0f pts)",
      _Symbol, InpVirtualMode ? "VIRTUAL PAPER" : "DEMO/LIVE",
      InpEnableHybridTP1 ? "ENABLED" : "DISABLED", InpTP1Points,
      g_virtual_balance,
      g_london_high, g_london_low, g_london_mid,
      g_london_range, q_text,
      status_text,
      InpEnableTrailing ? "ACTIVE" : "OFF", InpTrailStep1Pts, InpTrailStep2Pts
   );
   Comment(dash);
}

//+------------------------------------------------------------------+
//| CSV Logger for Python Daemon Interoperability                    |
//+------------------------------------------------------------------+
void InitCsvLog()
{
   int handle = FileOpen("aurum_gold_shadow_trades.csv", FILE_READ | FILE_WRITE | FILE_CSV | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      handle = FileOpen("aurum_gold_shadow_trades.csv", FILE_WRITE | FILE_CSV);
      if(handle != INVALID_HANDLE)
      {
         FileWrite(handle, "ticket", "time", "action", "symbol", "direction", "entry", "sl", "tp", "pnl", "r_mult", "reason", "balance");
         FileClose(handle);
      }
   }
   else
   {
      FileClose(handle);
   }
}

void LogTradeToCsv(const VirtualTrade &t, string action, double pnl, double r_mult, string reason)
{
   int handle = FileOpen("aurum_gold_shadow_trades.csv", FILE_READ | FILE_WRITE | FILE_CSV);
   if(handle != INVALID_HANDLE)
   {
      FileSeek(handle, 0, SEEK_END);
      FileWrite(handle,
                t.ticket,
                TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES),
                action,
                _Symbol,
                t.direction,
                DoubleToString(t.entry_price, 2),
                DoubleToString(t.sl, 2),
                DoubleToString(t.tp, 2),
                DoubleToString(pnl, 2),
                DoubleToString(r_mult, 2),
                reason,
                DoubleToString(g_virtual_balance, 2));
      FileClose(handle);
   }
}

void DrawHLine(string name, double price, color clr, string text, ENUM_LINE_STYLE style=STYLE_SOLID)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   }
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetString(0, name, OBJPROP_TOOLTIP, text);
}
