# AURUM Research Engine v0.3

محرك بحث وكمي متقدم لاختبار وتقييم فرضيات نطاق جلسة نيويورك (**Session Opening Range**) على:
- **US100** (Nasdaq 100)
- **XAUUSD** (الذهب)
- **US30** (Dow Jones 30)

---

## 1. الفرضيات الخمس المستقلة في v0.3

بدلاً من خلط الاستراتيجيات، يختبر المحرك 5 فرضيات منفصلة كلياً:
1. **Boundary Reversion**: ارتداد حقيقي عند أطراف النطاق ($Distance \le 0.20 \times \text{ATR}$) مع منع أي دخول بعيد خارج النطاق.
2. **Sweep → Reclaim**: سحب سيولة باختراق مؤقت خارج القمة أو القاع ثم العودة والإغلاق المؤكد داخل النطاق.
3. **Micro-Range Reversion**: اقتناص تذبذب النطاقات الصغيرة اللحظية المتكررة أثناء الجلسة.
4. **Momentum Breakout**: اختراق فوري بزخم شمعة قوية (نسبة جسم الشمعة $\ge 50\%$) وهامش ATR كافٍ.
5. **Breakout → Retest**: انتظار اختراق النطاق ثم إعادة اختبار المستوى المكسور والتأكيد قبل الدخول.

بالإضافة إلى:
- **Composite Regime (State Machine)**: نظام إدارة بيئة السوق التلقائي المبني على **Range Health Score**؛ يفعّل الارتداد في النطاقات المستقرة فقط، ويتحول إلى الاختراق عند تحول السوق إلى مسار اتجاهي (Trend).

---

## 2. إدارة التوقيت وتثبيت جلسة نيويورك

- **المنطقة الزمنية**: تحويل التوقيت إلى `America/New_York` تلقائياً لحساب التوقيت الصيفي والشتوي (DST).
- **افتتاح الجلسة**: مثبت على `09:30 AM` بتوقيت نيويورك المحلي.

---

## 3. أدوات التحقق الإحصائي والتحمل

1. **Cost & Slippage Stress Test**:
   - اختبار الاستراتيجية عبر مضاعفات السبريد ($\times 1.0, \times 1.25, \times 1.50, \times 2.0$) ومستويات الانزلاق السعري ($0, 1, 2, 5, 10$ تكات).
2. **Monte Carlo Resampling (1,000 جولة)**:
   - حساب فترات الثقة 95% لعائد R وتوزيع أقصى هبوط متوقع واحتمالية الربحية.
3. **Parameter Spectrum Matrix**:
   - فحص متانة فترات الـ Opening Range ($5, 10, 15, 20, 30, 45, 60$ دقيقة) ونوافذ الجلسة ($30$ إلى $150$ دقيقة) لكشف الـ Plateaus المستقرة مقابل الـ Spikes العشوائية.
4. **Rolling Walk-Forward**:
   - تدريب وفحص تدريجي عبر الأيام لتأكيد عدم وجود Look-ahead أو Curve Fitting.

---

## 4. التشغيل السريع

```bash
# تفعيل البيئة
source .venv/bin/activate

# 1. اختبار الفرضيات الخمس لـ US100
python -m src.main --xlsx Trading_Analysis_Consolidated.xlsx --symbol US100 --strategy all

# 2. تشغيل حزمة البحث الكاملة (Stress Test + Monte Carlo + Matrix + Walk-Forward)
python -m src.main --xlsx Trading_Analysis_Consolidated.xlsx --symbol US100 --full-suite

# 3. تشغيل حزمة البحث الكاملة لـ XAUUSD
python -m src.main --xlsx Trading_Analysis_Consolidated.xlsx --symbol XAUUSD --full-suite

# 4. توليد التقرير الموحد
python -m src.make_report

# 5. تشغيل الاختبارات الآلية (Unit Tests)
python -m pytest tests/test_engine.py -v
```

---

## 5. تصدير بيانات MT5 لعدة سنوات (Equiti Demo)

1. انسخ ملف [`src/mql5/AurumExport.mq5`](src/mql5/AurumExport.mq5) إلى منصة MT5 (`MQL5/Scripts`).
2. اسحب السكريبت إلى شارت الرمز المطلوب (`US100`, `US30`, `XAUUSD`) على فريم M1 لمدة 730+ يوم.
3. انقل الملف المصدّر من `MQL5/Files/` إلى مجلد `data/` لتشغيل أبحاث متعددة السنوات.
