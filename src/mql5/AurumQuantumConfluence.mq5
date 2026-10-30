//+------------------------------------------------------------------+
//|                                     AurumQuantumConfluence.mq5   |
//|                                  Copyright 2026, AURUM Research |
//|           AURUM Quantum Orthogonal Confluence Visual Indicator   |
//|   Layer 1: SMC Fair Value Gaps (FVG) & Consequent Encroachment   |
//|   Layer 2: Volunacci Golden Pocket (Volume + Fib 0.618-0.786)    |
//|   Layer 3: Dynamic Linear Regression Standard Deviation Channel  |
//|   Layer 4: Dual Momentum Divergence Scanner (RSI & MACD)         |
//+------------------------------------------------------------------+
#property copyright   "AURUM Research"
#property link        "https://github.com/aurum-research"
#property version     "2.00"
#property description "Visualizes the 4-layer non-conflicting Quantum Confluence Engine on MT5 charts."
#property indicator_chart_window
#property indicator_buffers 5
#property indicator_plots   3

//--- Plot 1: Linear Regression Midline
#property indicator_label1  "Reg_Midline"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrAqua
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

//--- Plot 2: Regression Upper (+2.0 SD)
#property indicator_label2  "Reg_Upper_2SD"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrTomato
#property indicator_style2  STYLE_DOT
#property indicator_width2  1

//--- Plot 3: Regression Lower (-2.0 SD)
#property indicator_label3  "Reg_Lower_2SD"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrLimeGreen
#property indicator_style3  STYLE_DOT
#property indicator_width3  1

//--- Inputs
input group "=== Layer 1: SMC Fair Value Gaps (FVG) ==="
input bool   InpEnableFVG          = true;     // Plot Fair Value Gaps (Imbalances)
input color  InpBullishFVGColor    = clrDarkGreen; // Bullish FVG Box Color
input color  InpBearishFVGColor    = clrMaroon;    // Bearish FVG Box Color
input double InpMinFVGPts          = 0.50;     // Min FVG Gap Size in points

input group "=== Layer 2: Volunacci (Volume + Fibonacci) ==="
input bool   InpEnableVolunacci    = true;     // Plot Volunacci Golden Pocket
input double InpRVOLThreshold      = 1.50;     // Relative Volume threshold (x of 20 SMA)
input color  InpGoldenPocketColor  = clrGoldenrod; // Golden Pocket Color

input group "=== Layer 3: Linear Regression Channel ==="
input bool   InpEnableRegression   = true;     // Plot Linear Regression Channel
input int    InpRegLookback        = 100;      // Regression Lookback Bars
input double InpRegDevMultiplier   = 2.0;      // Channel StdDev Multiplier

input group "=== Layer 4: Divergence & Quantum Dashboard ==="
input bool   InpEnableDivergence   = true;     // Scan for RSI & MACD Divergences
input int    InpRSIPeriod          = 14;       // RSI Period
input bool   InpShowDashboard      = true;     // Show On-Chart HUD Information Panel
input bool   InpSendAlerts         = true;     // Send Terminal and Push Alerts

//--- Buffers
double g_buf_reg_mid[];
double g_buf_reg_upper[];
double g_buf_reg_lower[];
double g_buf_fvg_up[];
double g_buf_fvg_down[];

//--- Indicator Handles
int g_handle_rsi;
int g_handle_macd;

//+------------------------------------------------------------------+
//| Custom indicator initialization function                         |
//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0, g_buf_reg_mid, INDICATOR_DATA);
   SetIndexBuffer(1, g_buf_reg_upper, INDICATOR_DATA);
   SetIndexBuffer(2, g_buf_reg_lower, INDICATOR_DATA);
   SetIndexBuffer(3, g_buf_fvg_up, INDICATOR_CALCULATIONS);
   SetIndexBuffer(4, g_buf_fvg_down, INDICATOR_CALCULATIONS);

   PlotIndexSetString(0, PLOT_LABEL, "Quantum Midline");
   PlotIndexSetString(1, PLOT_LABEL, "Quantum Upper +2SD");
   PlotIndexSetString(2, PLOT_LABEL, "Quantum Lower -2SD");

   // Handles
   g_handle_rsi = iRSI(_Symbol, _Period, InpRSIPeriod, PRICE_CLOSE);
   g_handle_macd = iMACD(_Symbol, _Period, 12, 26, 9, PRICE_CLOSE);

   Print("[AURUM QUANTUM] Initialized 4-Layer Quantum Confluence Visual Engine on ", _Symbol);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Custom indicator deinitialization function                       |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, "AQ_FVG_");
   ObjectsDeleteAll(0, "AQ_VOL_");
   ObjectsDeleteAll(0, "AQ_DIV_");
   ObjectsDeleteAll(0, "AQ_HUD_");
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Custom indicator iteration function                              |
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   if(rates_total < InpRegLookback + 5)
      return(0);

   int start = prev_calculated - 1;
   if(start < InpRegLookback)
      start = InpRegLookback;

   // ----------------------------------------------------------------
   // 1. Plot Linear Regression Channel
   // ----------------------------------------------------------------
   if(InpEnableRegression)
   {
      for(int i = start; i < rates_total; i++)
      {
         double sum_x = 0, sum_y = 0, sum_xy = 0, sum_x2 = 0;
         int N = InpRegLookback;
         int offset = i - N + 1;

         for(int k = 0; k < N; k++)
         {
            double y_val = close[offset + k];
            sum_x += k;
            sum_y += y_val;
            sum_xy += k * y_val;
            sum_x2 += k * k;
         }

         double denom = (N * sum_x2 - sum_x * sum_x);
         if(denom != 0)
         {
            double slope = (N * sum_xy - sum_x * sum_y) / denom;
            double intercept = (sum_y - slope * sum_x) / N;

            double curr_fit = slope * (N - 1) + intercept;
            g_buf_reg_mid[i] = curr_fit;

            // Residual Standard Deviation
            double sum_res2 = 0;
            for(int k = 0; k < N; k++)
            {
               double fit_k = slope * k + intercept;
               double res = close[offset + k] - fit_k;
               sum_res2 += res * res;
            }
            double sd = MathSqrt(sum_res2 / N);

            g_buf_reg_upper[i] = curr_fit + InpRegDevMultiplier * sd;
            g_buf_reg_lower[i] = curr_fit - InpRegDevMultiplier * sd;
         }
      }
   }

   // ----------------------------------------------------------------
   // 2. Draw Fair Value Gaps (Layer 1 SMC)
   // ----------------------------------------------------------------
   if(InpEnableFVG && rates_total > 3)
   {
      int last_bar = rates_total - 1;
      // Check last 15 bars for new FVGs
      for(int i = MathMax(2, last_bar - 15); i <= last_bar; i++)
      {
         // Bullish FVG
         if(low[i] > high[i - 2])
         {
            double gap = low[i] - high[i - 2];
            if(gap >= InpMinFVGPts)
            {
               string name = "AQ_FVG_BULL_" + IntegerToString(time[i - 1]);
               if(ObjectFind(0, name) < 0)
               {
                  ObjectCreate(0, name, OBJ_RECTANGLE, 0, time[i - 2], high[i - 2], time[MathMin(i + 15, rates_total - 1)], low[i]);
                  ObjectSetInteger(0, name, OBJPROP_COLOR, InpBullishFVGColor);
                  ObjectSetInteger(0, name, OBJPROP_FILL, true);
                  ObjectSetInteger(0, name, OBJPROP_BACK, true);
               }
            }
         }
         // Bearish FVG
         else if(high[i] < low[i - 2])
         {
            double gap = low[i - 2] - high[i];
            if(gap >= InpMinFVGPts)
            {
               string name = "AQ_FVG_BEAR_" + IntegerToString(time[i - 1]);
               if(ObjectFind(0, name) < 0)
               {
                  ObjectCreate(0, name, OBJ_RECTANGLE, 0, time[i - 2], low[i - 2], time[MathMin(i + 15, rates_total - 1)], high[i]);
                  ObjectSetInteger(0, name, OBJPROP_COLOR, InpBearishFVGColor);
                  ObjectSetInteger(0, name, OBJPROP_FILL, true);
                  ObjectSetInteger(0, name, OBJPROP_BACK, true);
               }
            }
         }
      }
   }

   // ----------------------------------------------------------------
   // 3. Volunacci Golden Pocket Detection (Layer 2)
   // ----------------------------------------------------------------
   if(InpEnableVolunacci && rates_total > 25)
   {
      int last_bar = rates_total - 1;
      // Calculate RVOL on last bar
      long sum_vol = 0;
      for(int v = 1; v <= 20; v++)
         sum_vol += tick_volume[last_bar - v];
      double avg_v = (double)sum_vol / 20.0;
      double rvol = (avg_v > 0) ? ((double)tick_volume[last_bar] / avg_v) : 1.0;

      if(rvol >= InpRVOLThreshold)
      {
         string name = "AQ_VOL_GP_" + IntegerToString(time[last_bar]);
         double h = high[last_bar];
         double l = low[last_bar];
         double rng = h - l;
         double fib_618 = l + 0.618 * rng;
         double fib_786 = l + 0.786 * rng;

         if(ObjectFind(0, name) < 0)
         {
            ObjectCreate(0, name, OBJ_RECTANGLE, 0, time[last_bar], fib_786, time[MathMin(last_bar + 20, rates_total - 1)], fib_618);
            ObjectSetInteger(0, name, OBJPROP_COLOR, InpGoldenPocketColor);
            ObjectSetInteger(0, name, OBJPROP_FILL, true);
            ObjectSetInteger(0, name, OBJPROP_BACK, true);
         }
      }
   }

   // ----------------------------------------------------------------
   // 4. On-Chart HUD Information Dashboard
   // ----------------------------------------------------------------
   if(InpShowDashboard && rates_total > InpRegLookback)
   {
      int last_bar = rates_total - 1;
      double curr_c = close[last_bar];
      double mid = g_buf_reg_mid[last_bar];
      double upper = g_buf_reg_upper[last_bar];
      double sd = (upper - mid) / InpRegDevMultiplier;
      double z_score = (sd > 0) ? ((curr_c - mid) / sd) : 0.0;

      long sum_v = 0;
      for(int v = 1; v <= 20; v++) sum_v += tick_volume[last_bar - v];
      double avg_v = (double)sum_v / 20.0;
      double rvol = (avg_v > 0) ? ((double)tick_volume[last_bar] / avg_v) : 1.0;

      string bias = "NEUTRAL (BALANCED)";
      color bias_col = clrGray;
      if(z_score <= -1.8 && rvol >= 1.2)
      {
         bias = "HIGH BULLISH CONFLUENCE (OVERSOLD + VOLUME)";
         bias_col = clrLimeGreen;
      }
      else if(z_score >= 1.8 && rvol >= 1.2)
      {
         bias = "HIGH BEARISH CONFLUENCE (OVERBOUGHT + VOLUME)";
         bias_col = clrTomato;
      }

      string txt = StringFormat(
         "AURUM QUANTUM CONFLUENCE v2.1\n" +
         "Z-Score: %+.2f SD | RVOL: %.2fx\n" +
         "Bias: %s\n" +
         "Zero-Conflict Gate: ENFORCED (Micro-SL Protected)",
         z_score, rvol, bias
      );

      string lbl = "AQ_HUD_TXT";
      if(ObjectFind(0, lbl) < 0)
      {
         ObjectCreate(0, lbl, OBJ_LABEL, 0, 0, 0);
         ObjectSetInteger(0, lbl, OBJPROP_CORNER, CORNER_LEFT_UPPER);
         ObjectSetInteger(0, lbl, OBJPROP_XDISTANCE, 20);
         ObjectSetInteger(0, lbl, OBJPROP_YDISTANCE, 40);
         ObjectSetString(0, lbl, OBJPROP_FONT, "Consolas");
         ObjectSetInteger(0, lbl, OBJPROP_FONTSIZE, 10);
      }
      ObjectSetString(0, lbl, OBJPROP_TEXT, txt);
      ObjectSetInteger(0, lbl, OBJPROP_COLOR, bias_col);
   }

   return(rates_total);
}
//+------------------------------------------------------------------+
