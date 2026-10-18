# eg4hosting pharmacy POS v0.9 — ETA eReceipt Foundation

## الجديد
- شاشة ETA Dashboard لمتابعة الإيصالات الإلكترونية وحالاتها.
- Offline queue محلي: الفاتورة تحفظ أولًا ثم تجهز للإرسال بدون تعطيل البيع.
- Snapshot JSON ثابت + SHA-256 لكل إيصال لمنع تغير محتوى الفاتورة بعد تجهيزها.
- إعدادات RIN / Branch Code / POS Serial / Activity Code / Client ID.
- Sandbox transport آمن للاختبار بدون إرسال بيانات حقيقية.
- Submission ID وUUID وحالة المحاولة وآخر خطأ وعدد مرات الإرسال.
- Queue للفواتير السابقة المتوافقة مع POS v0.5+.

## مهم قبل Production
v0.9 لا ترسل إلى Production عمدًا. يلزم بيانات تسجيل الصيدلية/POS واعتماد mapping النهائي على مواصفة ETA الحالية والتوقيع/Integration Toolkit الرسمي قبل فتح Production.

## مسار التشغيل
بيع -> حفظ الفاتورة -> Queue ETA -> Sandbox validation -> لاحقًا Production adapter بعد الاعتماد.
