//+------------------------------------------------------------------+
//|                                                  AurumExport.mq5 |
//|                                  Copyright 2026, AURUM Research |
//|                  Export clean M1/M5 OHLCV CSV for AURUM Engine   |
//+------------------------------------------------------------------+
#property copyright "AURUM Research"
#property link      "https://github.com/aurum-research"
#property version   "1.20"
#property script_show_inputs

//--- Input parameters
input int             InpDays        = 730;         // Number of days of history (default: 730)
input ENUM_TIMEFRAMES InpTimeframe   = PERIOD_M1;   // Timeframe to export (default: M1)
input string          InpSymbol      = "";          // Custom symbol name (leave empty for current chart)
input string          InpCustomFile  = "";          // Custom output filename (empty = auto)

//+------------------------------------------------------------------+
//| Helper to force download history from broker server              |
//+------------------------------------------------------------------+
bool SyncHistory(string sym, ENUM_TIMEFRAMES tf, datetime start_time)
{
   PrintFormat("[AURUM] Requesting history sync from broker for %s (%s)...", sym, EnumToString(tf));
   MqlRates test_rates[];
   
   // Ping CopyRates repeatedly to trigger MT5 server background download
   for(int i = 0; i < 25; i++)
   {
      if(IsStopped()) return false;
      int res = CopyRates(sym, tf, start_time, 50, test_rates);
      if(res > 0)
      {
         datetime first_date;
         SeriesInfoInteger(sym, tf, SERIES_FIRSTDATE, first_date);
         if(first_date > 0 && first_date <= start_time + 86400 * 7)
         {
            PrintFormat("[AURUM] History sync complete for %s. Earliest bar: %s", 
                        sym, TimeToString(first_date, TIME_DATE));
            return true;
         }
      }
      PrintFormat("[AURUM] Downloading history from server (%s)... attempt %d/25", sym, i + 1);
      Sleep(1000);
   }
   return false;
}

//+------------------------------------------------------------------+
//| Script program start function                                    |
//+------------------------------------------------------------------+
void OnStart()
{
   string sym = (InpSymbol == "") ? _Symbol : InpSymbol;
   
   // Ensure symbol is selected in Market Watch
   if(!SymbolSelect(sym, true))
   {
      PrintFormat("[ERROR] Failed to select symbol %s: error %d", sym, GetLastError());
      Alert("[ERROR] Symbol " + sym + " cannot be selected in Market Watch.");
      return;
   }

   datetime time_to   = TimeCurrent();
   datetime time_from = time_to - (InpDays * 86400);

   PrintFormat("[AURUM] Starting export of %d days for %s from %s to %s...", 
               InpDays, sym, TimeToString(time_from, TIME_DATE), TimeToString(time_to, TIME_DATE));

   // Ensure broker history is synchronized
   SyncHistory(sym, InpTimeframe, time_from);

   // Request rates
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   
   int copied = 0;
   for(int attempts = 0; attempts < 10; attempts++)
   {
      if(IsStopped()) return;
      copied = CopyRates(sym, InpTimeframe, time_from, time_to, rates);
      if(copied > 0) break;
      PrintFormat("[AURUM] Reading copied rates... attempt %d/10", attempts + 1);
      Sleep(1000);
   }

   if(copied <= 0)
   {
      PrintFormat("[ERROR] Failed to copy rates for %s. Error: %d.", sym, GetLastError());
      Alert("[ERROR] History for " + sym + " is still downloading or not provided by broker. Please switch chart to M1, scroll back, and retry.");
      return;
   }

   string tf_str = EnumToString(InpTimeframe);
   StringReplace(tf_str, "PERIOD_", "");

   string filename = InpCustomFile;
   if(filename == "")
   {
      filename = sym + "_" + tf_str + ".csv";
   }

   int file_handle = FileOpen(filename, FILE_WRITE | FILE_CSV | FILE_ANSI, ",");
   if(file_handle == INVALID_HANDLE)
   {
      PrintFormat("[ERROR] Failed to open file '%s' for writing: error %d", filename, GetLastError());
      Alert("[ERROR] Cannot open file " + filename + " for writing.");
      return;
   }

   // Write header
   FileWrite(file_handle, "time", "open", "high", "low", "close", "tick_volume");

   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);

   for(int i = 0; i < copied; i++)
   {
      string time_str = TimeToString(rates[i].time, TIME_DATE | TIME_MINUTES | TIME_SECONDS);
      StringReplace(time_str, ".", "-");

      FileWrite(file_handle,
         time_str,
         DoubleToString(rates[i].open, digits),
         DoubleToString(rates[i].high, digits),
         DoubleToString(rates[i].low, digits),
         DoubleToString(rates[i].close, digits),
         IntegerToString(rates[i].tick_volume)
      );
   }

   FileClose(file_handle);

   PrintFormat("[AURUM] SUCCESS: Exported %d bars for %s to 'MQL5/Files/%s'", copied, sym, filename);
   Alert("[AURUM] SUCCESS: Exported " + IntegerToString(copied) + " bars for " + sym + " to MQL5/Files/" + filename);
}
//+------------------------------------------------------------------+
