# 🏛️ AURUM Quantitative Desk - Windows Deployment Guide

دليل تشغيل وتثبيت مكتب AURUM الكمي على أنظمة Windows 10 و Windows 11.

---

## 🚀 التثبيت السريع (1-Click Setup)

1. **تأكد من وجود Python 3.10+**:
   - قم بتنزيله من [python.org](https://www.python.org/) وتأكد من تفعيل خيار **`Add Python to PATH`** أثناء التثبيت.

2. **التثبيت بنقرة واحدة**:
   - انقر مرتين (Double Click) على الملف: **`setup_windows.bat`**.
   - سيقوم بإنشاء البيئة الافتراضية، وتثبيت المكتبات، وتجهيز ملف المفاتيح `.env`، وفحص سلامة الكود.

3. **تشغيل المنصة الرسومية**:
   - انقر مرتين على **`run_streamlit.bat`** لفتح لوحة التحكم الرسومية التفاعلية على المتصفح (`http://localhost:8501`).

4. **تشغيل حارس التداول (Sentinel)**:
   - انقر مرتين على **`run_sentinel.bat`** لتشغيل محرك التيليجرام وفحص الفرص والربط مع MT5.

---

## 📊 ربط روبوتات MQL5 في منصة MetaTrader 5 (Windows)

1. افتح منصة **MetaTrader 5** على ويندوز.
2. من القائمة العلوية اضغط: `File` ➔ `Open Data Folder`.
3. ادخل المجلد: `MQL5\Experts`.
4. انسخ الملفين من مجلد `src/mql5/`:
   - `AurumH17ShadowEA.mq5` (لمؤشر US100 / Nasdaq).
   - `AurumGoldH17ShadowEA.mq5` (للذهب XAUUSD).
5. في MetaTrader 5 اضغط بزر الفأرة الأيمن على `Navigator ➔ Expert Advisors` ثم اختر `Refresh`.
6. اسحب الروبوت وضعه على شارت الدقيقة `M1` مع تفعيل خيار **`Allow Algo Trading`**.
