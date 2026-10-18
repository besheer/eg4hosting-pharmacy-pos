# eg4hosting pharmacy POS v1.0.0

## التعديلات
- بحث POS عربي/English بالاسم التجاري والعلمي والمادة الفعالة والشركة والتصنيف.
- `%` Wildcard + بحث متعدد الكلمات + AutoComplete + Enter workflow.
- دعم مخطط قاعدة Egyptian Drug Database CC0 (commercial_name_en/ar, scientific_name, manufacturer, drug_class, route, price_egp).
- أداة `IMPORT_EGYPTIAN_DRUGS.bat` لتحميل واستيراد قاعدة السوق المصري CC0 مباشرة عند توفر الإنترنت.
- بيانات الصيدلية عربي/English، عنوان، هاتف، WhatsApp، بريد، رقم ضريبي وسجل تجاري.
- رفع لوجو محلي وحفظه داخل إعدادات البرنامج.
- مسارات Backup / Export / Receipts قابلة للتعديل واختبار صلاحية الكتابة.
- Full Backup ZIP لقاعدة SQLite + settings + manifest مع Audit Log.
- Receipt Designer: 58/80mm وإظهار/إخفاء اللوجو والعنوان والهاتف والرقم الضريبي.
- Barcode Labels مع Code128/EAN عند توفر python-barcode.
- تحديث رقم الإصدار إلى v1.0.0.

## ملاحظة قاعدة الأدوية
ملف الـ25K+ غير مضمّن داخل ZIP لأن بيئة البناء الحالية لا تستطيع تنزيل الملف الثنائي/الكامل من GitHub إلى الحاوية. أداة الاستيراد مضمّنة وتستخدم المصدر CC0 مباشرة. بعد تشغيلها تصبح البيانات محلية داخل SQLite ولا يحتاج البحث للإنترنت.
