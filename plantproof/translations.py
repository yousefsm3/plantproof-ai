"""Arabic glosses for the dashboard (UI text only).

bi(text)       -> "text :small[:gray[ترجمة]]"  Streamlit markdown: English, then light-grey Arabic
bi_plain(text) -> "text · ترجمة"        for places that cannot show colour (dropdowns, tables, charts)

Text without a translation is returned unchanged, so a missing entry never breaks the app.
Engine-generated sentences (finding details with record IDs) stay in English.
"""

from __future__ import annotations

AR: dict[str, str] = {
    # --- navigation and sidebar
    "Overview": "نظرة عامة",
    "Evidence": "الأدلة",
    "What If": "ماذا لو",
    "Blind Test": "الاختبار الأعمى",
    "Cost": "التكلفة",
    "History": "السجل",
    "Handover": "تسليم الوردية",
    "Navigate": "التنقل",
    "Scenario": "السيناريو",
    "Evidence-first investigations for plant incidents": "تحقيقات قائمة على الأدلة لأعطال المصانع",
    "Saved history may be lost when the app restarts or redeploys. Export it from the History page to keep a copy.":
        "قد يُحذف السجل المحفوظ عند إعادة تشغيل التطبيق. صدّره من صفحة السجل للاحتفاظ بنسخة.",
    "Synthetic demo data only · Rule-based analysis, no external AI or API keys.":
        "بيانات تجريبية وهمية فقط · تحليل بالقواعد، بدون ذكاء اصطناعي خارجي أو مفاتيح API.",

    # --- scenarios
    "Scenario A - P-301 trip, 13 Oct 2026": "السيناريو أ - توقف المضخة P-301، 13 أكتوبر 2026",
    "Scenario B - P-301 trip, 20 Oct 2026": "السيناريو ب - توقف المضخة P-301، 20 أكتوبر 2026",
    "Cooling water pump P-301 (Line 3)": "مضخة ماء التبريد P-301 (الخط 3)",
    "analysis window": "فترة التحليل",

    # --- hypotheses and confidence levels
    "Bearing wear": "تآكل المحمل",
    "Vibration sensor fault": "عطل حساس الاهتزاز",
    "Pump cavitation": "تكهّف المضخة",
    "Shaft misalignment": "عدم محاذاة العمود",
    "High": "عالية",
    "Medium": "متوسطة",
    "Low": "منخفضة",
    "Base": "أساسي",
    "Cost case: Low": "منخفض",
    "Cost case: Base": "أساسي",
    "Cost case: High": "مرتفع",

    # --- sensors
    "Vibration (mm/s)": "الاهتزاز",
    "Bearing temp (°C)": "حرارة المحمل",
    "Discharge pressure (bar)": "ضغط التصريف",
    "Motor current (A)": "تيار المحرك",
    "Alarm": "حد الإنذار",
    "Linked to a contradiction": "مرتبط بتناقض",
    "Confidence": "الثقة",

    # --- overview
    "Records analysed": "السجلات المحللة",
    "Contradictions": "التناقضات",
    "Missing evidence": "الأدلة المفقودة",
    "Leading hypothesis": "الفرضية الأقوى",
    "Sensor trends": "اتجاهات الحساسات",
    "Hypothesis confidence": "ثقة الفرضيات",
    "Estimated cost impact if confirmed": "التكلفة المتوقعة إذا تأكد السبب",
    "Rule-based and explainable. See the Evidence page for the working.":
        "مبني على قواعد وقابل للتفسير. التفاصيل في صفحة الأدلة.",
    "No contradictions detected.": "لا توجد تناقضات.",
    "All required evidence is present.": "كل الأدلة المطلوبة موجودة.",
    "Needed to test": "مطلوب لاختبار",
    "Source records": "السجلات المصدر",
    "Records that conflict with each other. Resolve before restart.":
        "سجلات تتعارض مع بعضها. يجب حلها قبل إعادة التشغيل.",
    "Evidence a hypothesis needs that is absent or out of date.":
        "أدلة تحتاجها فرضية وهي غير موجودة أو قديمة.",

    # --- evidence page
    "Evidence engine": "محرك الأدلة",
    "Every conclusion below links to the source record IDs it is based on.":
        "كل نتيجة هنا مربوطة بأرقام السجلات التي بُنيت عليها.",
    "Hypothesis ranking": "ترتيب الفرضيات",
    "How confidence is calculated": "كيف تُحسب الثقة",
    "Support ratio": "نسبة الدعم",
    "Evidence coverage": "تغطية الأدلة",
    "Contested factor": "معامل التعارض",
    "Supporting evidence": "أدلة داعمة",
    "Refuting evidence": "أدلة نافية",
    "Recommended actions if confirmed": "الإجراءات الموصى بها إذا تأكد السبب",
    "No supporting rule matched.": "لم تنطبق أي قاعدة داعمة.",
    "No refuting rule matched.": "لم تنطبق أي قاعدة نافية.",
    "Trace a record": "تتبّع سجلًا",
    "Record ID used by a finding": "رقم سجل استُخدم في نتيجة",
    "Used by": "مستخدم في",
    "All source records": "كل السجلات المصدر",
    "Record types": "أنواع السجلات",
    "Save this investigation": "احفظ هذا التحقيق",
    "Title": "العنوان",
    "Analyst role": "دور المحلل",
    "Notes": "ملاحظات",
    "Save investigation": "حفظ التحقيق",
    "Investigation saved to History. Remember to export history to keep it.":
        "حُفظ التحقيق في السجل. تذكّر تصدير السجل للاحتفاظ به.",
    "Use a role, not a personal name - this demo is public.":
        "اكتب دورًا وليس اسمًا شخصيًا، فهذا العرض عام.",

    # --- engine rule labels (from config/hypotheses.json)
    "Online vibration above alarm": "الاهتزاز المباشر فوق حد الإنذار",
    "Bearing temperature above alarm": "حرارة المحمل فوق حد الإنذار",
    "Elevated iron in oil sample": "حديد مرتفع في عينة الزيت",
    "Handheld vibration confirms high level": "الجهاز اليدوي يؤكد ارتفاع الاهتزاز",
    "Oil iron content normal": "نسبة الحديد في الزيت طبيعية",
    "High vibration with normal bearing temperature": "اهتزاز عالٍ مع حرارة محمل طبيعية",
    "Handheld vibration reading is normal": "قراءة الجهاز اليدوي طبيعية",
    "Discharge pressure below alarm": "ضغط التصريف تحت حد الإنذار",
    "Motor current dropped": "انخفاض تيار المحرك",
    "Discharge pressure stable throughout": "ضغط التصريف مستقر طوال الفترة",
    "Alignment offset out of tolerance": "انحراف المحاذاة خارج الحد المسموح",
    "Alignment within tolerance": "المحاذاة ضمن الحد المسموح",
    "Online vibration trend": "منحنى الاهتزاز المباشر",
    "Bearing temperature trend": "منحنى حرارة المحمل",
    "Oil analysis (iron ppm)": "تحليل الزيت (الحديد)",
    "Vibration sensor calibration (within 12 months)": "معايرة حساس الاهتزاز (خلال 12 شهرًا)",
    "Independent handheld vibration check": "فحص اهتزاز مستقل بجهاز يدوي",
    "Discharge pressure trend": "منحنى ضغط التصريف",
    "Suction strainer differential pressure check": "فحص فرق الضغط في مصفاة الشفط",
    "Laser shaft alignment check": "فحص محاذاة العمود بالليزر",
    "Plan bearing replacement before restart": "خطط لاستبدال المحمل قبل إعادة التشغيل",
    "Inspect lubrication system and oil supply": "افحص نظام التزييت وتغذية الزيت",
    "Keep the failed bearing for root-cause inspection": "احتفظ بالمحمل التالف لفحص السبب الجذري",
    "Recalibrate or replace the vibration transmitter": "أعد معايرة حساس الاهتزاز أو استبدله",
    "Check sensor cabling and mounting": "افحص أسلاك الحساس وتثبيته",
    "Restart under close monitoring with handheld checks": "أعد التشغيل مع مراقبة دقيقة وفحوصات يدوية",
    "Check suction strainer and inlet valve position": "افحص مصفاة الشفط ووضع صمام الدخول",
    "Verify tank level and NPSH margin": "تحقق من مستوى الخزان وهامش ضغط الشفط",
    "Perform laser shaft alignment": "نفّذ محاذاة العمود بالليزر",
    "Check baseplate bolts and soft foot": "افحص مسامير القاعدة وثبات الأرجل",
    "Operator log reports normal while sensors are in alarm":
        "سجل المشغّل يقول «طبيعي» بينما الحساسات في حالة إنذار",
    "Inspection reports normal while sensors are in alarm":
        "الفحص يقول «طبيعي» بينما الحساسات في حالة إنذار",
    "Handheld vibration vs online vibration sensor disagree":
        "الجهاز اليدوي والحساس المباشر غير متفقين",

    # --- advisor
    "Advisor": "المساعد الذكي",
    "Engineering advisor": "المساعد الهندسي",
    "Rule-based assistant: every answer comes from this investigation's evidence and What If simulations. No external AI.":
        "مساعد مبني على القواعد: كل إجابة من أدلة هذا التحقيق ومحاكاة ماذا لو، بدون ذكاء اصطناعي خارجي.",
    "Suggested questions": "أسئلة مقترحة",
    "Clear conversation": "امسح المحادثة",
    "Ask a question about this investigation, then use the suggested questions or type your own.":
        "اسأل عن هذا التحقيق: استخدم الأسئلة المقترحة أو اكتب سؤالك.",
    # --- what if
    "What If simulations": "محاكاة ماذا لو",
    "Changes are applied to a copy of the data. Original observations are never modified - each run proves this with a fingerprint check.":
        "التغييرات تُطبّق على نسخة من البيانات، والأصل لا يتغير أبدًا، وكل تجربة تثبت ذلك ببصمة رقمية.",
    "Start from a preset": "ابدأ من تجربة جاهزة",
    "Custom": "مخصص",
    "Ignore these record types": "تجاهل أنواع السجلات هذه",
    "Override one record's value": "غيّر قيمة سجل واحد",
    "Record": "السجل",
    "New value": "القيمة الجديدة",
    "Scale a sensor parameter": "اضرب قراءات حساس في معامل",
    "Parameter": "المتغير",
    "Multiply all readings by": "اضرب كل القراءات في",
    "Add hypothetical evidence": "أضف دليلًا افتراضيًا",
    "Value": "القيمة",
    "Run simulation": "شغّل المحاكاة",
    "Choose a preset or build custom changes, then run the simulation.":
        "اختر تجربة جاهزة أو ابنِ تغييراتك، ثم شغّل المحاكاة.",
    "Applied": "التغييرات المطبقة",
    "Changes": "التغييرات",
    "Original data fingerprint (before → after)": "بصمة البيانات الأصلية (قبل ← بعد)",
    "Original observations unchanged (memory and database checked).":
        "البيانات الأصلية لم تتغير (فُحصت الذاكرة وقاعدة البيانات).",
    "Contradictions resolved": "تناقضات حُلّت",
    "New contradictions": "تناقضات جديدة",
    "Evidence gaps closed": "فجوات أدلة أُغلقت",
    "New evidence gaps": "فجوات أدلة جديدة",
    "Save this run to History": "احفظ هذه التجربة في السجل",
    "What If run saved.": "حُفظت التجربة.",
    "Baseline": "الوضع الأصلي",
    "Alignment check finds a 0.32 mm offset": "فحص المحاذاة يجد انحرافًا 0.32 مم",
    "Alignment check within tolerance (0.03 mm)": "فحص المحاذاة ضمن الحد المسموح (0.03 مم)",
    "Oil analysis comes back clean (15 ppm iron)": "تحليل الزيت سليم (15 جزءًا من المليون حديد)",
    "New sensor calibration certificate issued today": "شهادة معايرة جديدة للحساس اليوم",
    "Handheld check at trip time reads 3.0 mm/s": "الفحص اليدوي وقت التوقف يقرأ 3.0 مم/ث",
    "Ignore all operator logs": "تجاهل كل سجلات المشغّلين",
    "Laser alignment check (offset, mm)": "فحص المحاذاة بالليزر (الانحراف، مم)",
    "Suction strainer check (differential pressure, bar)": "فحص مصفاة الشفط (فرق الضغط، بار)",
    "Handheld vibration check (mm/s)": "فحص الاهتزاز اليدوي (مم/ث)",
    "Oil analysis (iron, ppm)": "تحليل الزيت (الحديد)",
    "New vibration sensor calibration certificate": "شهادة معايرة جديدة لحساس الاهتزاز",
    "Discharge pressure reading (bar)": "قراءة ضغط التصريف (بار)",

    # --- blind test
    "Score the engine": "قيّم المحرك",
    "Score your own analysis": "قيّم تحليلك أنت",
    "Run Blind Test": "شغّل الاختبار الأعمى",
    "Blind Test score": "نتيجة الاختبار الأعمى",
    "Grade": "التقدير",
    "Excellent": "ممتاز",
    "Good": "جيد",
    "Partial": "جزئي",
    "Needs review": "يحتاج مراجعة",
    "Reveal reference answers": "اكشف الإجابات المرجعية",
    "Root cause": "السبب الجذري",
    "Expected contradictions": "التناقضات المتوقعة",
    "Expected missing evidence": "الأدلة المفقودة المتوقعة",
    "Rationale": "التبرير",
    "Save result to History": "احفظ النتيجة في السجل",
    "Blind Test result saved.": "حُفظت نتيجة الاختبار.",
    "Most likely root cause": "السبب الأرجح",
    "Second most likely": "السبب الثاني",
    "Records involved in contradictions": "سجلات فيها تناقضات",
    "Evidence that is missing or out of date": "أدلة مفقودة أو قديمة",
    "Score my analysis": "قيّم تحليلي",
    "Runs the engine's current analysis through the scorer.": "يمرّر تحليل المحرك الحالي على أداة التقييم.",
    "Make your own call from the Evidence page, then see how you score.":
        "اتخذ قرارك من صفحة الأدلة، ثم شاهد نتيجتك.",
    "Scores an analysis against reference answers stored separately in data/reference_answers.json. The evidence engine never reads that file (a unit test enforces this).":
        "يقيّم التحليل مقابل إجابات مرجعية محفوظة في ملف منفصل، ومحرك الأدلة لا يقرأ هذا الملف أبدًا (يتحقق اختبار آلي من ذلك).",
    "Transparency note: this repository is public, so anyone can read the reference answers. The separation shows the method; it is not a secret.":
        "ملاحظة شفافية: المستودع عام، فيمكن لأي أحد قراءة الإجابات المرجعية. الفصل يوضح المنهجية وليس سرًا.",
    "Component": "العنصر",
    "Points": "النقاط",
    "Detail": "التفاصيل",

    # --- cost
    "Cost impact simulator": "محاكي أثر التكلفة",
    "Low / base / high totals with every assumption and formula visible. All figures are illustrative synthetic values.":
        "تقديرات منخفضة وأساسية ومرتفعة، مع ظهور كل افتراض ومعادلة. كل الأرقام توضيحية.",
    "Cost the repair for": "احسب تكلفة إصلاح",
    "Adjust assumptions (this session only)": "عدّل الافتراضات (لهذه الجلسة فقط)",
    "Downtime (hours)": "مدة التوقف (ساعات)",
    "Labour (hours)": "ساعات العمل",
    "Parts (£)": "قطع الغيار (£)",
    "Lost margin (£/hour)": "الربح الضائع (£/ساعة)",
    "Labour rate (£/hour)": "أجر العمل (£/ساعة)",
    "Repair scope": "نطاق الإصلاح",
    "Breakdown": "التفصيل",
    "Inputs used": "المدخلات المستخدمة",
    "Confidence-weighted base cost": "التكلفة الأساسية الموزونة بالثقة",
    "Expected base cost across hypotheses": "التكلفة الأساسية المتوقعة لكل الفرضيات",
    "Lost production": "الإنتاج الضائع",
    "Repair labour": "عمالة الإصلاح",
    "Parts": "قطع الغيار",

    # --- history
    "Investigation history": "سجل التحقيقات",
    "Export history": "تصدير السجل",
    "Import history": "استيراد السجل",
    "Import file": "استورد الملف",
    "Show all scenarios": "اعرض كل السيناريوهات",
    "Investigations": "التحقيقات",
    "What If runs": "تجارب ماذا لو",
    "Blind Tests": "الاختبارات العمياء",
    "Handovers": "التسليمات",
    "Nothing saved yet.": "لا يوجد شيء محفوظ بعد.",
    "Delete": "حذف",
    "Danger zone": "منطقة الخطر",
    "I understand this cannot be undone": "أفهم أنه لا يمكن التراجع عن هذا",
    "Clear all history": "امسح كل السجل",
    "Reset demo observations": "أعد ضبط بيانات العرض",
    "Storage notice": "تنبيه التخزين",
    "History may be wiped when the app restarts, reboots, redeploys or wakes from sleep. Download it below and import it again later.":
        "قد يُحذف السجل عند إعادة تشغيل التطبيق أو تحديثه أو استيقاظه من السكون. نزّله من هنا واستورده لاحقًا.",

    # --- handover
    "Shift handover": "تسليم الوردية",
    "Built from engine findings and your notes - no AI text generation. Use role names, not personal names: this demo is public.":
        "مبني من نتائج المحرك وملاحظاتك، بدون توليد نص بالذكاء الاصطناعي. اكتب أدوارًا وليس أسماء، فالعرض عام.",
    "Shift": "الوردية",
    "Outgoing (role)": "المسلِّم (الدور)",
    "Incoming (role)": "المستلِم (الدور)",
    "Include cost impact for the leading hypothesis": "أضف التكلفة للفرضية الأقوى",
    "Include latest What If result": "أضف آخر نتيجة ماذا لو",
    "Notes for the incoming shift": "ملاحظات للوردية القادمة",
    "Generate handover": "أنشئ تقرير التسليم",
    "Markdown report": "تقرير Markdown",
    "JSON data": "بيانات JSON",
    "Save to History": "احفظ في السجل",
    "Handover saved.": "حُفظ التسليم.",
    "Previous handovers": "التسليمات السابقة",
    "Day shift (06:00–18:00)": "الوردية النهارية",
    "Night shift (18:00–06:00)": "الوردية الليلية",
    # handover report headings (preview only)
    "Status": "الحالة",
    "Contradictions to resolve": "تناقضات يجب حلها",
    "Actions for incoming shift": "إجراءات للوردية القادمة",
    "Cost impact (illustrative)": "أثر التكلفة (توضيحي)",
    "What If notes": "ملاحظات ماذا لو",
    "Analyst notes": "ملاحظات المحلل",
}


def ar(text: str) -> str:
    """Arabic gloss for text, or '' if there is none."""
    return AR.get(text, "")


def bi(text: str) -> str:
    """Streamlit markdown: English followed by light-grey Arabic."""
    gloss = ar(text)
    return f"{text} :small[:gray[{gloss}]]" if gloss else text


def bi_plain(text: str) -> str:
    """Plain text: 'English · عربي' for dropdowns, tables and charts."""
    gloss = ar(text)
    return f"{text} · {gloss}" if gloss else text
