# 🏛️ AURUM Quantitative Desk - Linux Deployment Guide

دليل تشغيل مكتب AURUM الكمي على أنظمة Linux (Ubuntu / Debian / Arch / Oracle Linux).

---

## 🚀 التشغيل السريع (1-Click Setup)

```bash
# 1. إعطاء تصاريح التشغيل
chmod +x setup_linux.sh run_linux.sh

# 2. تشغيل مثبت النظام التلقائي (يثبت الحزم وينشئ بيئة Python ويفحص الاختبارات)
./setup_linux.sh

# 3. تشغيل المنصة الرسومية (Streamlit Web Dashboard)
./run_linux.sh web

# 4. تشغيل حارس التداول الآلي 24/7 (Sentinel Daemon)
./run_linux.sh sentinel
```

---

## ⚙️ التثبيت كخدمة خلفية دائمة (Systemd Daemon 24/7)

لتشغيل حارس التداول في الخلفية باستمرار حتى بعد إغلاق الطرفية:

```bash
sudo cp -r . /home/ubuntu/aurum_research  # أو مسار مجلدك الحالي

# إنشاء ملف الخدمة
sudo tee /etc/systemd/system/aurum-sentinel.service > /dev/null << 'EOF'
[Unit]
Description=AURUM 24/7 Cloud Trading Sentinel & Intelligence Daemon
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/aurum_research
Environment="PYTHONPATH=/home/ubuntu/aurum_research"
ExecStart=/home/ubuntu/aurum_research/.venv/bin/python -m src.shadow_daemon --mode watch --interval 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# تفعيل وتشغيل الخدمة
sudo systemctl daemon-reload
sudo systemctl enable --now aurum-sentinel

# فحص الحالة
systemctl status aurum-sentinel
```
