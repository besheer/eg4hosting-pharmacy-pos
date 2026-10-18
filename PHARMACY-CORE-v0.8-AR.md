# eg4hosting pharmacy POS v0.8 — Egyptian Catalog & Safety

## الجديد
- استيراد/تحديث قاعدة الأدوية بالجملة من CSV أو XLSX.
- دعم عربي/English، المادة الفعالة/الاسم العلمي، GTIN/Barcode، الشركة، الشكل، التركيز، السعر والتصنيف.
- استيراد بيانات الدليل الدوائي مع `source` وتاريخ المصدر.
- Smart Alternatives: اقتراح المثائل حسب المادة الفعالة ثم التركيز والشكل الدوائي.
- Interaction Checker مبني على قواعد موثقة قابلة للإدارة، مع Minor/Moderate/Major/Contraindicated.
- شاشة إدارة قواعد التفاعلات ومصدر كل قاعدة.
- لا توجد قواعد تفاعلات طبية تجريبية مزروعة افتراضيًا حتى لا يعرض النظام تحذيرات غير موثقة.

## أعمدة الاستيراد المقترحة
`barcode, trade_name, arabic_name, generic_name, generic_name_ar, strength, dosage_form, manufacturer, category, price, indications, contraindications, warnings, side_effects, interactions, dispensing_level, source, source_updated`

> المعلومات الطبية Decision Support للصيدلي وليست بديلًا عن مصدر دوائي معتمد أو الحكم المهني.
